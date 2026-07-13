$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$temp = Join-Path ([IO.Path]::GetTempPath()) ("ato-cold-" + [guid]::NewGuid().ToString("N"))
$artifacts = Join-Path $temp "artifacts"
$pythonArtifacts = Join-Path $artifacts "python"
$npmArtifacts = Join-Path $artifacts "npm"

function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}

try {
    New-Item -ItemType Directory -Force -Path $pythonArtifacts, $npmArtifacts | Out-Null
    Push-Location $repo
    python -m build packages/core --outdir $pythonArtifacts
    Assert-Exit "Python build"
    pnpm run build
    Assert-Exit "TypeScript build"
    Push-Location (Join-Path $repo "packages\shared")
    pnpm pack --pack-destination $npmArtifacts
    Assert-Exit "Shared pack"
    Pop-Location
    Push-Location (Join-Path $repo "packages\cli")
    pnpm pack --pack-destination $npmArtifacts
    Assert-Exit "CLI pack"
    Pop-Location
    Push-Location (Join-Path $repo "packages\mcp-server")
    pnpm pack --pack-destination $npmArtifacts
    Assert-Exit "MCP pack"
    Pop-Location
    Push-Location $repo
    pnpm pack --pack-destination $npmArtifacts
    Assert-Exit "Root pack"
    Pop-Location

    $venv = Join-Path $temp "venv"
    python -m venv $venv
    Assert-Exit "venv creation"
    $venvPython = Join-Path $venv "Scripts\python.exe"
    $wheels = @(Get-ChildItem -LiteralPath $pythonArtifacts -Filter "*.whl")
    if ($wheels.Count -ne 1) { throw "Expected one wheel, found $($wheels.Count)" }
    $wheel = $wheels[0]
    & $venvPython -m pip install --disable-pip-version-check $wheel.FullName
    Assert-Exit "wheel installation"

    $npmProject = Join-Path $temp "npm-project"
    New-Item -ItemType Directory -Path $npmProject | Out-Null
    Push-Location $npmProject
    npm init -y | Out-Null
    $tarballs = @(Get-ChildItem -LiteralPath $npmArtifacts -Filter "*.tgz" | ForEach-Object { $_.FullName })
    if ($tarballs.Count -ne 4) { throw "Expected four npm tarballs, found $($tarballs.Count)" }
    npm install --ignore-scripts @tarballs
    Assert-Exit "npm tarball installation"

    $env:ATO_PYTHON = $venvPython
    $ato = Join-Path $npmProject "node_modules\.bin\ato.cmd"
    & $ato --version
    Assert-Exit "ato version"
    & $ato doctor
    Assert-Exit "ato doctor"
    & $ato roles
    Assert-Exit "ato roles"
    & $venvPython -c "import ato_core; from ato_core.models.role import RoleLoader; assert 'architect' in RoleLoader().list_roles(); print(ato_core.__version__)"
    Assert-Exit "ato_core import"

    $mcpEntry = Join-Path $npmProject "node_modules\@spacesky-cell\agent-team-orchestrator\bin\ato-mcp.js"
    node (Join-Path $repo "scripts\e2e\mcp-smoke.mjs") $mcpEntry
    Assert-Exit "MCP startup"
    Pop-Location
    Write-Output "Cold installation passed"
}
finally {
    Set-Location $repo
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
