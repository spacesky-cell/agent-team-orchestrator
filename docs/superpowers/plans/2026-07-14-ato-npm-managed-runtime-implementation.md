# ATO npm Managed Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `v0.2.1` so one global npm install provides working `ato` and `ato-mcp` commands on machines with Node.js 18+ and Python 3.10+, without a separate user-managed pip install.

**Architecture:** The root npm tarball embeds the version-matched Python wheel and a hash manifest. Root shims disclose that manifest before dynamically importing the existing adapters; `@spacesky-cell/ato-shared` lazily creates and reuses a versioned virtual environment while Python `ato_core` remains the sole owner of orchestration semantics.

**Tech Stack:** Node.js 18 ESM, TypeScript 5, Vitest, pnpm 9 workspaces, Python 3.10+, Hatchling/build, pytest, PowerShell and Bash release gates.

## Global Constraints

- Release version is exactly `0.2.1`; do not rewrite or delete public tag `v0.2.0`.
- The supported user install command is `npm install --global @spacesky-cell/agent-team-orchestrator`.
- Require Node.js 18+ and a system Python 3.10+; do not bundle an interpreter.
- Do not use npm `postinstall`, publish `ato-core` to PyPI, or install into global/project Python.
- `ato --version` and help must not create the managed runtime.
- MCP and JSON stdout remain protocol-only; bootstrap diagnostics go to stderr.
- Generated `vendor/`, Python dist files, npm tarballs, release artifacts, and manifests remain uncommitted.
- Publish exact verified tarballs in dependency order: shared, CLI, MCP, root.

---

### Task 1: Managed Python Runtime Owner

**Files:**
- Create: `packages/shared/src/managed-runtime.ts`
- Create: `packages/shared/src/managed-runtime.test.ts`
- Modify: `packages/shared/src/index.ts`

**Interfaces:**
- Consumes: `PythonRuntime` from `packages/shared/src/protocol.ts`, a generated JSON manifest, filesystem/process primitives, and optional injected dependencies for deterministic tests.
- Produces: `ManagedRuntimeStatus`, `ManagedRuntimeOptions`, `ManagedRuntimeError`, and `ensureManagedRuntime(manifestPath, options): Promise<PythonRuntime>`.

- [x] **Step 1: Add manifest and path RED tests**

  Add table-driven Vitest cases that write temporary manifests and assert exact stable codes for unsupported fields/schema, non-semver versions, package/core mismatch, traversal outside the vendor directory, missing wheel, hash mismatch, and Python below 3.10. Add platform path cases for `ATO_HOME`, Windows `LOCALAPPDATA`, macOS Application Support, Linux `XDG_DATA_HOME`, and Linux home fallback.

  ```ts
  await expect(ensureManagedRuntime(manifest, harness.options)).rejects.toMatchObject({
    code: "BUNDLED_RUNTIME_INVALID",
  });
  expect(harness.runtimeRoot("linux", { ATO_HOME: "/ato" })).toBe("/ato/runtime/0.2.1");
  ```

- [x] **Step 2: Verify the manifest/path tests fail for the missing module**

  Run: `pnpm exec vitest run packages/shared/src/managed-runtime.test.ts`

  Expected: FAIL because `./managed-runtime.js` cannot be resolved.

- [x] **Step 3: Implement strict validation, hashing, storage selection, and typed errors**

  Implement exact-field JSON validation, realpath/relative containment checks, streamed SHA-256, semver parsing, Python version probing, platform-specific storage roots, bounded/redacted messages, and these error codes:

  ```ts
  type ManagedRuntimeErrorCode =
    | "PYTHON_NOT_FOUND"
    | "PYTHON_VERSION_UNSUPPORTED"
    | "BUNDLED_RUNTIME_INVALID"
    | "MANAGED_RUNTIME_BUSY"
    | "MANAGED_RUNTIME_INSTALL_FAILED";
  ```

- [x] **Step 4: Add installation lifecycle RED tests**

  Use injected subprocess/filesystem timing hooks to cover successful venv creation, marker content, cache reuse without pip, corrupt marker rebuild, exclusive lock wait, stale lock recovery, lock timeout, bounded subprocess timeout, credential/token redaction, temporary-directory cleanup, and lock cleanup.

  ```ts
  expect(harness.commands.map((command) => command.stage)).toEqual(["venv", "pip", "probe"]);
  await ensureManagedRuntime(manifest, harness.options);
  expect(harness.commands.filter((command) => command.stage === "pip")).toHaveLength(1);
  ```

- [x] **Step 5: Verify lifecycle tests fail on missing behavior**

  Run: `pnpm exec vitest run packages/shared/src/managed-runtime.test.ts`

  Expected: validation cases pass and lifecycle cases FAIL because installation/locking is not implemented.

- [x] **Step 6: Implement bounded installation, locking, atomic promotion, and cache probing**

  Use exclusive lock creation, a 180-second waiter with 500 ms probes, ten-minute stale-lock recovery, UUID temporary directory, 120-second venv timeout, 600-second pip timeout, 10-second probes, 1 MiB process-output cap, 4 KiB redacted error cap, atomic marker writes, containment checks before removal, rename promotion, and `finally` cleanup. Export the module from `src/index.ts`.

- [x] **Step 7: Verify Task 1**

  Run: `pnpm exec vitest run packages/shared/src/managed-runtime.test.ts && pnpm --filter @spacesky-cell/ato-shared lint && pnpm --filter @spacesky-cell/ato-shared build`

  Expected: all focused tests pass, ESLint reports zero warnings, and TypeScript build exits 0.

- [x] **Step 8: Commit Task 1**

  ```bash
  git add packages/shared/src/managed-runtime.ts packages/shared/src/managed-runtime.test.ts packages/shared/src/index.ts
  git commit -m "feat(shared): provision managed Python runtime"
  ```

### Task 2: Discovery Fallback and Protocol-Safe Status

**Files:**
- Modify: `packages/shared/src/python-discovery.ts`
- Modify: `packages/shared/src/python-discovery.test.ts`
- Modify: `packages/cli/src/app.ts`
- Modify: `packages/cli/src/app.test.ts`
- Modify: `packages/mcp-server/src/bin.ts`
- Create: `packages/mcp-server/src/bin.test.ts`

**Interfaces:**
- Consumes: `ensureManagedRuntime`, `ATO_BUNDLED_RUNTIME_MANIFEST`, existing probe order, and stderr callbacks.
- Produces: `DiscoveryOptions.onManagedRuntimeStatus`, injectable `prepareManagedRuntime`, and lazy CLI/MCP bridge setup sharing the same managed runtime.

- [ ] **Step 1: Add discovery and adapter RED tests**

  Cover existing-core precedence, managed fallback only after candidates fail, no-manifest `PYTHON_NOT_FOUND`, failed `ATO_PYTHON` retained as managed base, CLI bootstrap statuses on stderr only when a bridge command runs, MCP bootstrap statuses on stderr with empty stdout, and no discovery for version/help.

  ```ts
  expect(await discoverPython({ env: { ATO_BUNDLED_RUNTIME_MANIFEST: manifest }, prepareManagedRuntime })).toEqual(managed);
  expect(stdout).toEqual([]);
  expect(stderr.join("\n")).toContain("Preparing ATO Python runtime");
  ```

- [ ] **Step 2: Verify the new tests fail for missing fallback/status behavior**

  Run: `pnpm exec vitest run packages/shared/src/python-discovery.test.ts packages/cli/src/app.test.ts packages/mcp-server/src/bin.test.ts`

  Expected: FAIL on missing discovery options and MCP/CLI status routing.

- [ ] **Step 3: Implement fallback and status wiring**

  Record failed base candidates without exposing probe errors, delegate once to `ensureManagedRuntime` when the manifest exists, pass the first executable base candidate to managed provisioning, keep CLI creation lazy, and provide concise stage messages through `console.error` for CLI and MCP.

- [ ] **Step 4: Verify Task 2**

  Run: `pnpm exec vitest run packages/shared/src/python-discovery.test.ts packages/cli/src/app.test.ts packages/mcp-server/src/bin.test.ts && pnpm run typecheck`

  Expected: all focused tests and workspace type checks pass.

- [ ] **Step 5: Commit Task 2**

  ```bash
  git add packages/shared/src/python-discovery.ts packages/shared/src/python-discovery.test.ts packages/cli/src/app.ts packages/cli/src/app.test.ts packages/mcp-server/src/bin.ts packages/mcp-server/src/bin.test.ts
  git commit -m "feat(adapters): discover bundled managed runtime"
  ```

### Task 3: Root Shims and Bundled Wheel Preparation

**Files:**
- Modify: `bin/ato.js`
- Modify: `bin/ato-mcp.js`
- Modify: `packages/cli/src/package-entry.test.ts`
- Create: `scripts/release/prepare-npm-runtime.mjs`
- Create: `scripts/release/prepare-npm-runtime.test.mjs`
- Modify: `package.json`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: one `ato_core-0.2.1-py3-none-any.whl` from a Python artifact directory.
- Produces: `vendor/ato-core.whl`, `vendor/runtime-manifest.json`, and root shims that set `ATO_BUNDLED_RUNTIME_MANIFEST` before importing adapter code.

- [ ] **Step 1: Add shim and preparation RED tests**

  Extend package-entry tests to assert dynamic imports occur after the environment assignment. Add Node test cases for zero/multiple/wrong-version wheels and for a valid wheel producing stable filename, exact manifest keys, and matching lowercase SHA-256.

  ```js
  assert.deepEqual(Object.keys(manifest).sort(), ["coreVersion", "packageVersion", "schemaVersion", "sha256", "wheel"]);
  assert.equal(manifest.wheel, "ato-core.whl");
  ```

- [ ] **Step 2: Verify preparation tests fail**

  Run: `node --test scripts/release/prepare-npm-runtime.test.mjs && pnpm exec vitest run packages/cli/src/package-entry.test.ts`

  Expected: FAIL because the preparation script and dynamic shim behavior do not exist.

- [ ] **Step 3: Implement atomic vendor preparation and dynamic shims**

  Resolve paths from `import.meta.url`, refuse version drift, copy through temporary files, atomically replace generated files, set the internal manifest variable only when absent, and use top-level `await import(...)`. Add `vendor` to root package `files`, add a `prepare:npm-runtime` script, and ignore `/vendor/`.

- [ ] **Step 4: Verify Task 3**

  Run: `node --test scripts/release/prepare-npm-runtime.test.mjs && pnpm exec vitest run packages/cli/src/package-entry.test.ts && pnpm run build`

  Expected: preparation and shim tests pass and all packages build.

- [ ] **Step 5: Commit Task 3**

  ```bash
  git add bin/ato.js bin/ato-mcp.js packages/cli/src/package-entry.test.ts scripts/release/prepare-npm-runtime.mjs scripts/release/prepare-npm-runtime.test.mjs package.json .gitignore
  git commit -m "feat(package): embed Python core wheel"
  ```

### Task 4: npm-Only Artifact and Cold-Install Gates

**Files:**
- Modify: `scripts/e2e/cold-install.ps1`
- Modify: `scripts/e2e/cold-install.sh`
- Modify: `scripts/e2e/mcp-smoke.mjs`
- Modify: `scripts/release/build-manifest.mjs`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: Python dist output, prepared `vendor/`, four packed npm tarballs, clean temporary `ATO_HOME`.
- Produces: reproducible six-artifact checksum manifest and Windows/Linux npm-only install evidence.

- [ ] **Step 1: Change cold-install scripts into a failing npm-only gate**

  Remove temporary venv creation, wheel pip install, and `ATO_PYTHON`. Prepare the root vendor payload before packing, install only the four tarballs with `--ignore-scripts`, set a temporary `ATO_HOME`, assert no pre-existing `ato_core`, run version/doctor/roles/MCP, capture the managed executable, and run doctor twice while asserting the second invocation emits no install stage.

- [ ] **Step 2: Run the Windows gate and verify RED**

  Run: `./scripts/e2e/cold-install.ps1`

  Expected: FAIL before implementation integration is complete, at managed runtime provisioning or artifact inspection rather than manual pip setup.

- [ ] **Step 3: Harden artifact inspection, MCP failure smoke, and workflows**

  Reject root tarballs missing both vendor files, reject packed `workspace:` specs, assert MCP startup never writes protocol-invalid stdout, keep generated payloads uncommitted, upload Python wheel/sdist plus four npm tarballs and manifest, and run Linux MyPy on Python 3.10 and 3.12.

- [ ] **Step 4: Verify Task 4 locally**

  Run: `./scripts/e2e/cold-install.ps1`

  Expected: `ato --version`, `ato doctor`, `ato roles`, repeated runtime reuse, and MCP stdio startup all pass using npm tarballs only.

- [ ] **Step 5: Commit Task 4**

  ```bash
  git add scripts/e2e/cold-install.ps1 scripts/e2e/cold-install.sh scripts/e2e/mcp-smoke.mjs scripts/release/build-manifest.mjs .github/workflows/ci.yml .github/workflows/release.yml
  git commit -m "ci: verify npm-only cold installation"
  ```

### Task 5: User and Maintainer Documentation

**Files:**
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `docs/QUICKSTART.md`
- Modify: `docs/MCP_GUIDE.md`
- Modify: `docs/EXAMPLES.md`
- Modify: `docs/architecture.md`
- Modify: `CONTRIBUTING.md`
- Modify: `SECURITY.md`
- Modify: `.env.example`
- Modify: `packages/shared/README.md`
- Modify: `packages/cli/README.md`
- Modify: `packages/mcp-server/README.md`
- Modify: `packages/core/README.md`

**Interfaces:**
- Consumes: the verified npm-only behavior and platform runtime paths.
- Produces: one public install path, explicit prerequisites/first-run behavior, advanced override guidance, adapter caveats, uninstall cleanup, and architecture/security truth.

- [ ] **Step 1: Rewrite all public setup paths**

  Replace public two-layer and PyPI instructions with the global npm command. State Node.js 18+, Python 3.10+, possible first-command dependency download, `ATO_HOME`, platform storage paths, deliberate runtime removal, and that `ATO_PYTHON` is an advanced override. Keep `pip install -e "packages/core[dev]"` only in contributor setup.

- [ ] **Step 2: Synchronize architecture, MCP, package, and security docs**

  Document root-owned wheel/manifest, shared-owned provisioning, Python-owned business truth, stderr-only bootstrap status, standalone adapter limitations, hash/lock bounds, and no automatic runtime deletion.

- [ ] **Step 3: Verify documentation has no stale public path**

  Run:

  ```powershell
  $public = @('README.md','README_CN.md','docs/QUICKSTART.md','docs/MCP_GUIDE.md','packages/cli/README.md','packages/mcp-server/README.md','packages/core/README.md')
  Select-String -LiteralPath $public -Pattern 'pip install ato-core|pip uninstall ato-core|Install both runtime layers|PyPI' -CaseSensitive:$false
  ```

  Expected: no matches. Manually confirm English and Chinese quickstarts show the same supported npm command.

- [ ] **Step 4: Commit Task 5**

  ```bash
  git add README.md README_CN.md docs/QUICKSTART.md docs/MCP_GUIDE.md docs/EXAMPLES.md docs/architecture.md CONTRIBUTING.md SECURITY.md .env.example packages/shared/README.md packages/cli/README.md packages/mcp-server/README.md packages/core/README.md
  git commit -m "docs: publish npm-only installation path"
  ```

### Task 6: Version `0.2.1` and Release Metadata

**Files:**
- Modify: `package.json`
- Modify: `packages/shared/package.json`
- Modify: `packages/cli/package.json`
- Modify: `packages/mcp-server/package.json`
- Modify: `packages/core/package.json`
- Modify: `packages/core/pyproject.toml`
- Modify: `packages/core/src/ato_core/__init__.py`
- Modify: `packages/cli/src/app.ts`
- Modify: `packages/cli/src/app.test.ts`
- Modify: `pnpm-lock.yaml`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: completed feature commits since `v0.2.0`.
- Produces: exact `0.2.1` metadata everywhere and a dated release changelog.

- [ ] **Step 1: Update all first-party versions and exact workspace specs**

  Set every package, Python core, CLI-reported version, and workspace spec to `0.2.1`; regenerate only the pnpm lockfile metadata with `pnpm install --lockfile-only`; do not alter unrelated dependency versions.

- [ ] **Step 2: Add the `0.2.1` changelog entry**

  Add `## 0.2.1 - 2026-07-14` with Features, Fixes, Documentation, and Security/Packaging notes describing one-command npm installation, lazy managed runtime, npm-only cold-install gates, and bounded/redacted bootstrap failures.

- [ ] **Step 3: Verify exact version consistency**

  Run a Node script that parses all JSON/TOML/text sources and exits non-zero unless every first-party version/spec is `0.2.1`, then run `pnpm install --frozen-lockfile`.

  Expected: consistency script and frozen install exit 0; third-party `forwarded@0.2.0` remains untouched.

- [ ] **Step 4: Commit Task 6**

  ```bash
  git add package.json packages/shared/package.json packages/cli/package.json packages/mcp-server/package.json packages/core/package.json packages/core/pyproject.toml packages/core/src/ato_core/__init__.py packages/cli/src/app.ts packages/cli/src/app.test.ts pnpm-lock.yaml CHANGELOG.md
  git commit -m "chore: release v0.2.1"
  ```

### Task 7: Complete Verification, Push, Publish, and GitHub Release

**Files:**
- Generate only: `release-artifacts/python/*`, `release-artifacts/npm/*`, `release-manifest.json`, `vendor/*`
- No committed source changes unless a failing gate reveals a defect, in which case return to the relevant TDD task and commit the fix before continuing.

**Interfaces:**
- Consumes: clean `main` at the release commit, npm token via temporary `.npmrc`, GitHub credentials via temporary process environment.
- Produces: pushed `main`, public `v0.2.1`, four npm packages at `0.2.1`, verified registry cold install, and GitHub Release with checksum manifest.

- [ ] **Step 1: Run the complete local gate from a clean artifact state**

  Run: `pnpm run verify`, then `./scripts/e2e/cold-install.ps1`, `git diff --check`, `git status --short`, and a secret/placeholder scan.

  Expected: all checks pass; only ignored generated release artifacts exist; no token, `TODO`, `TBD`, or `workspace:` dependency appears in packed artifacts.

- [ ] **Step 2: Build immutable release artifacts once**

  Build Python wheel/sdist, prepare vendor, build TypeScript, pack shared/CLI/MCP/root in order, inspect tar contents/metadata, and generate SHA-256 for exactly six artifacts. Record their paths and hashes; do not rebuild after any registry publication.

- [ ] **Step 3: Push `main` and wait for GitHub CI**

  Run: `git push origin main`. Query the GitHub Actions API until the exact pushed SHA has completed successfully for all required workflows. Do not tag or publish on a failed/unknown run.

- [ ] **Step 4: Create/push `v0.2.1` and wait for tag CI**

  Run: `git tag v0.2.1` and `git push origin v0.2.1`. Verify the remote tag SHA and wait for the tag workflow to finish successfully.

- [ ] **Step 5: Publish exact npm tarballs with ephemeral authentication**

  Create a temporary userconfig containing the supplied token without printing it, publish shared, CLI, MCP, and root tarballs with `npm publish <exact-tarball> --userconfig <temp> --access public`, verify `npm view <name>@0.2.1 version dist.integrity`, and delete the temporary file in `finally`.

- [ ] **Step 6: Run public-registry npm-only cold install**

  In a fresh directory with no `ATO_PYTHON` and a temporary `ATO_HOME`, install exact root `0.2.1`, then run `ato --version`, `ato doctor`, `ato roles`, repeated doctor reuse, and MCP stdio startup. Confirm the installed root resolves exact adapter versions.

- [ ] **Step 7: Create and verify GitHub Release**

  Create GitHub Release `v0.2.1` from the existing tag, use the `0.2.1` changelog as notes, attach `release-manifest.json`, then query GitHub and npm to verify release/tag/SHA/assets/package versions. Ensure no PyPI publication occurred.

- [ ] **Step 8: Final repository and registry audit**

  Run `git status --short --branch`, verify `origin/main` equals local `HEAD`, verify `v0.2.1` equals `HEAD`, and verify all generated/credential temporary files are absent or ignored.

  Expected: clean tracked worktree, green local/remote gates, four public npm packages, successful public cold install, and one GitHub Release for `v0.2.1`.
