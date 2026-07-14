# 2026-07-14 ATO npm Managed Runtime Design

## Goal

Ship Agent Team Orchestrator through one public installation command:

```bash
npm install --global @spacesky-cell/agent-team-orchestrator
```

The installed `ato` and `ato-mcp` commands must work without a separate `pip install`.
The machine must already have Python 3.10 or newer. On the first command that needs the
Python core, ATO installs the wheel bundled in the root npm package and its dependencies
into a versioned, ATO-owned virtual environment. Later commands reuse that environment.

## Non-Goals

- Do not bundle a Python interpreter or platform-specific Python distributions in npm.
- Do not publish `ato-core` to PyPI for this release.
- Do not install into the user's global Python, project `.venv`, or active environment.
- Do not run Python installation from npm `postinstall`.
- Do not move orchestration, task, approval, or tool policy truth into TypeScript.
- Do not make the separately installable CLI or MCP npm packages self-provisioning; the
  root npm package is the supported user entry point.
- Do not rewrite or delete the already public `v0.2.0` tag. The npm-only release is
  `v0.2.1`.
- Do not implement offline dependency vendoring or automatic pruning of old runtimes in
  this release.

## Current Evidence

- `bin/ato.js` and `bin/ato-mcp.js` are thin root shims that immediately import the CLI
  and MCP packages. They do not provide Python.
- `packages/shared/src/python-discovery.ts` only accepts an executable that can already
  import `ato_core`.
- `packages/cli/src/app.ts` and `packages/mcp-server/src/bin.ts` both use shared Python
  discovery before calling `python -m ato_core.bridge`.
- `scripts/e2e/cold-install.ps1` and `scripts/e2e/cold-install.sh` currently create a
  separate virtual environment, install the wheel with pip, and set `ATO_PYTHON` before
  exercising npm. That proves the npm package is not self-contained.
- Root `package.json` does not include a wheel or runtime manifest in `files`.
- The `v0.2.0` tag points to `5bae5133274f49e8d312ea51c69dc85e7d46077b` and is public,
  but no `v0.2.0` GitHub Release or npm `0.2.0` publication exists.
- The user explicitly chose the recommended boundary: system Python 3.10+ is required,
  first-run dependency download is allowed, and no more design questions are required.

## Source of Truth and Owner Layer

Python `ato_core` remains the only owner of orchestration, task state, approvals, tools,
audit, worker health, bridge schemas, and role resources.

`packages/shared/src/managed-runtime.ts` owns only the Node-side installation boundary:
validating the bundled runtime manifest, selecting a base Python, creating a virtual
environment, installing the bundled wheel, and returning the managed Python executable.
It must not infer task status or authorization.

`packages/shared/src/python-discovery.ts` remains the single Python selection entry point.
It probes existing explicit/project/system runtimes first and delegates to the managed
runtime only when the root npm shim supplied a bundled runtime manifest.

The root npm package owns the bundled wheel and manifest. Root bin shims only disclose
their absolute manifest path through an internal environment variable before dynamically
importing CLI or MCP adapters.

## Proposed Design

### 1. Root npm package payload

The root tarball contains:

```text
bin/ato.js
bin/ato-mcp.js
vendor/ato-core.whl
vendor/runtime-manifest.json
```

`runtime-manifest.json` is generated, not hand-edited:

```json
{
  "schemaVersion": 1,
  "packageVersion": "0.2.1",
  "coreVersion": "0.2.1",
  "wheel": "ato-core.whl",
  "sha256": "<64 lowercase hex characters>"
}
```

`scripts/release/prepare-npm-runtime.mjs` receives the Python dist directory and vendor
directory. It requires exactly one `ato_core-0.2.1-py3-none-any.whl`, checks that the wheel
filename version equals root `package.json`, copies it to the stable vendor filename,
calculates SHA-256, and writes the manifest atomically. The generated `vendor/` directory
is ignored by Git and included by root `package.json`.

The root shims resolve `vendor/runtime-manifest.json` relative to `import.meta.url`, set
`ATO_BUNDLED_RUNTIME_MANIFEST` only when the caller did not already set it, then dynamically
import the existing CLI or MCP entry point. Dynamic import is required because static ESM
imports execute before the shim can set the environment variable.

### 2. Discovery and managed runtime interfaces

Shared exports these contracts:

```ts
export type ManagedRuntimeStatus =
  | "checking"
  | "creating"
  | "installing"
  | "ready";

export interface ManagedRuntimeOptions {
  env?: NodeJS.ProcessEnv;
  platform?: NodeJS.Platform;
  homeDir?: string;
  onStatus?: (status: ManagedRuntimeStatus, message: string) => void;
  timeoutMs?: number;
}

export async function ensureManagedRuntime(
  manifestPath: string,
  options?: ManagedRuntimeOptions,
): Promise<PythonRuntime>;
```

`DiscoveryOptions` gains `onManagedRuntimeStatus` and injectable runtime preparation for
unit tests. `discoverPython()` follows this order:

1. Probe `ATO_PYTHON` when present.
2. Probe the project `.venv` executable when present.
3. Probe `python3`/`python` in platform order.
4. If `ATO_BUNDLED_RUNTIME_MANIFEST` is present, call `ensureManagedRuntime()`.
5. Otherwise throw the existing bounded, secret-free `PYTHON_NOT_FOUND` error.

An explicit Python without `ato_core` may still be used as the base interpreter for the
managed environment; ATO never installs into that interpreter itself.

### 3. Managed storage

The runtime root is:

- `ATO_HOME/runtime/<coreVersion>` when `ATO_HOME` is set.
- `%LOCALAPPDATA%/AgentTeamOrchestrator/runtime/<coreVersion>` on Windows.
- `~/Library/Application Support/AgentTeamOrchestrator/runtime/<coreVersion>` on macOS.
- `${XDG_DATA_HOME:-~/.local/share}/agent-team-orchestrator/runtime/<coreVersion>` on Linux.

The ready directory contains the virtual environment and `ato-runtime.json`. The marker
records schema version, core version, wheel SHA-256, Python executable, and completion time.
Every selection probes the managed executable with a bounded command and requires its
reported `ato_core.__version__` to equal the manifest. A missing, corrupt, or mismatched
environment is rebuilt under the installation lock.

No project file, task output, API key, pip output, or model content is stored in this
runtime directory.

### 4. Safe installation and concurrency

Before any subprocess starts, shared validates:

- The manifest has exactly the supported fields and `schemaVersion === 1`.
- Versions are numeric `major.minor.patch` strings and package/core versions match.
- The wheel resolves inside the manifest directory.
- The wheel exists and its SHA-256 equals the manifest.
- The chosen base Python reports version 3.10 or newer.

Installation uses a version-scoped lock file opened with exclusive create. The lock is
bounded to 180 seconds. A waiter probes for a completed runtime every 500 ms. A lock older
than ten minutes is considered stale and may be replaced. The lock contains only PID and
timestamp.

The lock owner creates `<coreVersion>.tmp-<uuid>`, then runs:

```text
<base-python> -m venv <temporary-directory>
<temporary-python> -m pip install --disable-pip-version-check --no-input <bundled-wheel>
<temporary-python> -c <version probe>
```

Venv creation is limited to 120 seconds, pip installation to 600 seconds, and probes to
10 seconds. Output is bounded to 1 MiB at process level. Persisted errors contain at most
4 KiB after URL credentials and secret-like values are redacted. Full pip logs are not
persisted.

After verification, the marker is written atomically and the temporary directory is
renamed to the final version directory. Invalid old final directories are removed only
while holding the lock and only after path containment checks. Temporary directories and
the lock are cleaned in `finally` blocks.

### 5. User-visible behavior

`ato --version` and help continue to return immediately because CLI bridge creation stays
lazy. Commands that require the bridge emit concise installation status to stderr on the
first run. JSON and MCP stdout remain machine-only.

Successful `ato doctor` reports the managed Python executable and `core_version: 0.2.1`.
Subsequent commands do not run pip when the marker and live probe match.

If Python is missing, too old, the wheel is corrupt, the lock times out, or pip fails, the
command exits non-zero with one of these stable codes:

- `PYTHON_NOT_FOUND`
- `PYTHON_VERSION_UNSUPPORTED`
- `BUNDLED_RUNTIME_INVALID`
- `MANAGED_RUNTIME_BUSY`
- `MANAGED_RUNTIME_INSTALL_FAILED`

Errors name the failed stage and remediation without including tokens, authenticated index
URLs, or unbounded subprocess output.

`ATO_PYTHON` remains supported for advanced users and development. It does not create a
second compatibility package and does not change Python business ownership.

### 6. Packaging and release flow

The release version is `0.2.1` across root, shared, CLI, MCP, private core wrapper, Python
metadata, Python `__version__`, CLI version, MCP version, and lockfile workspace specs.

Build order is:

1. Build and verify Python wheel/sdist.
2. Run `prepare-npm-runtime.mjs` to create root `vendor/`.
3. Build TypeScript packages.
4. Pack shared, CLI, MCP, then root.
5. Inspect root tarball for the wheel and manifest and reject `workspace:` dependencies.
6. Cold-install only the four npm tarballs in a clean project with no preinstalled
   `ato_core` and no `ATO_PYTHON`.
7. Generate the six-artifact SHA-256 manifest.
8. Publish npm shared, CLI, MCP, then root from those exact bytes.
9. Cold-install exact public npm `0.2.1` with a temporary `ATO_HOME`.
10. Create GitHub Release `v0.2.1` and attach the local manifest.

The Python wheel and sdist remain GitHub/CI artifacts but are not uploaded to PyPI. The
root npm tarball is the distribution channel for the wheel.

### 7. Documentation and compatibility

Root English and Chinese READMEs, quickstart, MCP guide, examples, architecture,
contributing guide, security policy, package READMEs, and `.env.example` are synchronized
to one supported user path. The PyPI badge and public `pip install ato-core` instructions
are removed. Python 3.10+ remains an explicit prerequisite.

The standalone shared/CLI/MCP packages remain publishable because the root package depends
on exact matching versions. Their package READMEs state that end users should install the
root package; direct adapter installation requires a valid `ATO_PYTHON`.

Uninstalling npm does not silently delete the managed runtime or task output. Documentation
names the platform data directory and `ATO_HOME` override so users can remove it deliberately.

The public `v0.2.0` tag remains as an unreleased build. No registry package or GitHub Release
is created for it. `v0.2.1` is the first npm-only release.

## Alternatives Considered

### npm `postinstall`

Rejected. It performs network and Python mutations during package installation, makes
`npm install --ignore-scripts` produce a broken package, complicates protocol-safe logging,
and surprises users who only wanted to inspect the package.

### Bundle Python interpreters and all dependencies

Rejected. It multiplies artifacts across Windows, macOS, Linux, x64, and arm64; substantially
increases package size; and creates a Python security update responsibility outside the
project's current scope.

### Publish npm adapters without the core

Rejected. A fresh `npm install` would succeed but every real command would fail with
`PYTHON_NOT_FOUND`, directly violating the user-visible goal.

## Migration or Compatibility Policy

- Preserve `ATO_PYTHON` and direct adapter behavior for advanced users.
- Replace, rather than retain, the two-command public install path in current docs.
- Do not add a `src.*` Python alias, shared output directory fallback, or no-op approval.
- Do not rewrite `v0.2.0`; publish the corrected contract as `v0.2.1`.
- Do not publish `ato-core` to PyPI in this release.

## Acceptance Checks

- Unit tests cover manifest schema, traversal denial, hash mismatch, Python version floor,
  platform paths, successful install, cache reuse, corrupt rebuild, lock wait, stale lock,
  timeout, pip failure redaction, and cleanup.
- Discovery tests cover existing-core precedence, managed fallback, no-manifest failure,
  and explicit Python as a base without global installation.
- Root shim tests prove the manifest environment variable is set before dynamic import and
  that CLI/MCP import has no process-start side effect.
- `pnpm run verify` passes Black, Ruff, strict MyPy, ESLint, TypeScript, 70% Python coverage,
  TypeScript coverage, and all builds.
- Linux MyPy targets Python 3.10 and 3.12 without ignored `ato_core` modules.
- Root tarball contains `vendor/ato-core.whl` and `vendor/runtime-manifest.json`; every npm
  dependency is a registry version, never `workspace:`.
- Windows and Linux cold-install scripts install npm tarballs only, set a temporary
  `ATO_HOME`, and prove `ato --version`, `ato doctor`, `ato roles`, and MCP startup outside
  the repository without `ATO_PYTHON` or a prior core install.
- A second `ato doctor` reuses the same managed Python and does not invoke pip.
- Failure smoke tests keep MCP stdout empty and place bounded diagnostics on stderr.
- Public-registry cold install of exact npm `0.2.1` passes before GitHub Release creation.
- Remote `main`, `v0.2.1`, CI runs, npm metadata, GitHub Release, and attached manifest are
  verified after publication.

## Risks

- `design_risk`: First run depends on Python package indexes being reachable. Mitigation:
  explicit bounded error, no partial final runtime, and safe retry on the next command.
- `design_risk`: Concurrent CLI/MCP first runs can race. Mitigation: exclusive version lock,
  ready probing, stale lock recovery, temporary install, and atomic promotion.
- `design_risk`: A prepared wheel can drift from npm metadata. Mitigation: exact version
  match, SHA-256 runtime manifest, tarball inspection, immutable release manifest, and cold
  install from exact artifacts.
- `design_risk`: Pip diagnostics can contain authenticated index URLs. Mitigation: redact
  before display, truncate output, and persist no install logs.
- `recorded_debt`: Old managed runtime versions are not automatically pruned. They are
  version-isolated and documented for deliberate removal.
- `recorded_debt`: Direct installation of adapter packages still needs `ATO_PYTHON`. The
  root package is the only supported end-user entry point.
- `unrelated_optimization`: Bundling Python or offline dependency wheels is not part of
  this release.

## Review Changelog

- `blocking`: none.
- `design_risk`: first-run network, concurrency, artifact drift, and diagnostic redaction
  are bounded by the mechanisms and acceptance checks above.
- `recorded_debt`: runtime pruning and standalone adapter provisioning are intentionally
  deferred.
- `accepted`: lazy bootstrap, root-owned bundled wheel, shared runtime provisioning,
  version `0.2.1`, and no PyPI publication.
- `rejected`: postinstall, bundled interpreter, npm adapters without core, and rewriting
  the public `v0.2.0` tag.

## Open Questions

None. The user authorized the recommended path and asked not to be interrupted for routine
design decisions.
