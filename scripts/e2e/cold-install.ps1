$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runId = [guid]::NewGuid().ToString("N").Substring(0, 8)
$temp = Join-Path ([IO.Path]::GetTempPath()) ("ac-" + $runId)
$temporaryAtoHome = Join-Path ([IO.Path]::GetTempPath()) ("ah-" + $runId)
$artifacts = Join-Path $temp "artifacts"
$pythonArtifacts = Join-Path $artifacts "python"
$npmArtifacts = Join-Path $artifacts "npm"
$vendor = Join-Path $repo "vendor"
$originalPath = $env:PATH
$originalAtoHome = $env:ATO_HOME
$originalAtoPython = $env:ATO_PYTHON
$originalManifest = $env:ATO_BUNDLED_RUNTIME_MANIFEST
$originalPythonNoUserSite = $env:PYTHONNOUSERSITE
$vendorCreated = $false

function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}

function Restore-Environment([string]$Name, [AllowNull()][string]$Value) {
    if ($null -eq $Value) {
        Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
    }
    else {
        Set-Item -LiteralPath "Env:$Name" -Value $Value
    }
}

function Invoke-Captured(
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$StdoutPath,
    [string]$StderrPath,
    [string]$Step
) {
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -Wait -NoNewWindow -PassThru `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
    if ($process.ExitCode -ne 0) {
        $diagnostic = Get-Content -LiteralPath $StderrPath -Raw -ErrorAction SilentlyContinue
        throw "$Step failed with exit code $($process.ExitCode): $diagnostic"
    }
    return Get-Content -LiteralPath $StdoutPath -Raw
}

try {
    if (Test-Path -LiteralPath $vendor) {
        throw "Refusing to overwrite existing generated vendor directory: $vendor"
    }
    New-Item -ItemType Directory -Force -Path $pythonArtifacts, $npmArtifacts | Out-Null
    Push-Location $repo
    python -m build packages/core --outdir $pythonArtifacts
    Assert-Exit "Python build"
    $vendorCreated = $true
    node scripts/release/prepare-npm-runtime.mjs $pythonArtifacts $vendor
    Assert-Exit "npm runtime preparation"
    pnpm run build
    Assert-Exit "TypeScript build"

    foreach ($package in @("packages\shared", "packages\cli", "packages\mcp-server", ".")) {
        Push-Location (Join-Path $repo $package)
        pnpm pack --pack-destination $npmArtifacts
        Assert-Exit "Pack $package"
        Pop-Location
    }
    Pop-Location

    $tarballs = @(Get-ChildItem -LiteralPath $npmArtifacts -Filter "*.tgz")
    if ($tarballs.Count -ne 4) { throw "Expected four npm tarballs, found $($tarballs.Count)" }
    $rootTarball = $null
    foreach ($tarball in $tarballs) {
        $packageJsonText = (tar -xOf $tarball.FullName package/package.json | Out-String)
        Assert-Exit "Inspect $($tarball.Name) package.json"
        if ($packageJsonText -match 'workspace:') {
            throw "$($tarball.Name) contains an unpublished workspace dependency"
        }
        $packedPackage = $packageJsonText | ConvertFrom-Json
        if ($packedPackage.name -eq "@spacesky-cell/agent-team-orchestrator") {
            $rootTarball = $tarball
        }
    }
    if ($null -eq $rootTarball) { throw "Root npm tarball was not produced" }
    $rootFiles = @(tar -tf $rootTarball.FullName)
    Assert-Exit "Inspect root tarball files"
    foreach ($required in @("package/vendor/ato-core.whl", "package/vendor/runtime-manifest.json")) {
        if ($required -notin $rootFiles) { throw "Root tarball is missing $required" }
    }

    $cleanBase = Join-Path $temp "clean-base-python"
    python -m venv $cleanBase
    Assert-Exit "Clean base Python creation"
    $cleanScripts = Join-Path $cleanBase "Scripts"
    $cleanPython = Join-Path $cleanScripts "python.exe"
    $env:PATH = "$cleanScripts$([IO.Path]::PathSeparator)$originalPath"
    $env:PYTHONNOUSERSITE = "1"
    Remove-Item -LiteralPath Env:ATO_PYTHON -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath Env:ATO_BUNDLED_RUNTIME_MANIFEST -ErrorAction SilentlyContinue
    & $cleanPython -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('ato_core') is None else 1)"
    Assert-Exit "Clean base Python must not contain ato_core"

    $npmProject = Join-Path $temp "npm-project"
    New-Item -ItemType Directory -Path $npmProject | Out-Null
    Push-Location $npmProject
    npm init -y | Out-Null
    npm install --ignore-scripts @($tarballs.FullName)
    Assert-Exit "npm tarball installation"

    $env:ATO_HOME = $temporaryAtoHome
    $ato = Join-Path $npmProject "node_modules\.bin\ato.cmd"
    $version = (& $ato --version | Out-String).Trim()
    Assert-Exit "ato version"
    $expectedVersion = ((Get-Content -LiteralPath (Join-Path $repo "package.json") -Raw) | ConvertFrom-Json).version
    if ($version -ne $expectedVersion) { throw "Expected ato $expectedVersion, received $version" }
    if (Test-Path -LiteralPath (Join-Path $env:ATO_HOME "runtime")) {
        throw "ato --version created the managed runtime"
    }

    $firstOutput = Join-Path $temp "first-doctor.stdout"
    $firstError = Join-Path $temp "first-doctor.stderr"
    $doctorText = Invoke-Captured $ato @("doctor") $firstOutput $firstError "first ato doctor"
    $doctor = $doctorText | ConvertFrom-Json
    if ($doctor.core_version -ne $expectedVersion) {
        throw "Managed core version $($doctor.core_version) differs from $expectedVersion"
    }
    $managedRoot = [IO.Path]::GetFullPath((Join-Path $env:ATO_HOME "runtime"))
    if (-not [IO.Path]::GetFullPath([string]$doctor.python).StartsWith($managedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "doctor selected Python outside ATO_HOME: $($doctor.python)"
    }
    $firstDiagnostic = Get-Content -LiteralPath $firstError -Raw
    if ($firstDiagnostic -notmatch "Installing bundled ATO core") {
        throw "First doctor did not report managed runtime installation"
    }

    $rolesOutput = Join-Path $temp "roles.stdout"
    $rolesError = Join-Path $temp "roles.stderr"
    Invoke-Captured $ato @("roles") $rolesOutput $rolesError "ato roles" | Out-Null
    $secondOutput = Join-Path $temp "second-doctor.stdout"
    $secondError = Join-Path $temp "second-doctor.stderr"
    $secondDoctor = (Invoke-Captured $ato @("doctor") $secondOutput $secondError "second ato doctor") | ConvertFrom-Json
    if ($secondDoctor.python -ne $doctor.python) { throw "Second doctor selected a different runtime" }
    $secondDiagnostic = Get-Content -LiteralPath $secondError -Raw
    if ($secondDiagnostic -match "Creating an isolated|Installing bundled") {
        throw "Second doctor attempted to reinstall the managed runtime"
    }

    $mcpEntry = Join-Path $npmProject "node_modules\@spacesky-cell\agent-team-orchestrator\bin\ato-mcp.js"
    node (Join-Path $repo "scripts\e2e\mcp-smoke.mjs") $mcpEntry
    Assert-Exit "MCP startup"
    $env:ATO_BUNDLED_RUNTIME_MANIFEST = Join-Path $temp "missing-runtime-manifest.json"
    node (Join-Path $repo "scripts\e2e\mcp-smoke.mjs") $mcpEntry --expect-failure BUNDLED_RUNTIME_INVALID
    Assert-Exit "MCP failure diagnostics"
    Pop-Location
    Write-Output "npm-only cold installation passed"
}
finally {
    Set-Location $repo
    $env:PATH = $originalPath
    Restore-Environment "ATO_HOME" $originalAtoHome
    Restore-Environment "ATO_PYTHON" $originalAtoPython
    Restore-Environment "ATO_BUNDLED_RUNTIME_MANIFEST" $originalManifest
    Restore-Environment "PYTHONNOUSERSITE" $originalPythonNoUserSite
    if ($vendorCreated) {
        Remove-Item -LiteralPath $vendor -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $temporaryAtoHome -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
