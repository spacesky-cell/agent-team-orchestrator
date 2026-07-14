# Contributing

## Setup

```bash
git clone https://github.com/spacesky-cell/agent-team-orchestrator.git
cd agent-team-orchestrator
python -m pip install -e "packages/core[dev]"
pnpm install --frozen-lockfile
```

Python 3.10 and 3.12 plus Node.js 20 are exercised in CI. pnpm 9 is the lockfile owner; do not add `package-lock.json`.

## Architecture rule

Business truth belongs in `packages/core/src/ato_core`. CLI and MCP code are adapters over `python -m ato_core.bridge`; do not add embedded Python scripts, direct task-file readers, inferred completion, or no-op approvals to Node packages.

## Development loop

Write a failing test first, run it to confirm the expected failure, implement the smallest behavior, then run the focused test and the complete gate.

```bash
pnpm run verify
```

That command enforces Black, Ruff, strict MyPy, ESLint with zero warnings, TypeScript no-emit checks, Python coverage >=70%, TypeScript coverage, and all builds.

Package changes also require a cold-install check:

```powershell
./scripts/e2e/cold-install.ps1
```

```bash
./scripts/e2e/cold-install.sh
```

The cold-install gates build the Python wheel, embed it in the root npm tarball, and install only the four npm tarballs into a clean project. They must run without `ATO_PYTHON` or a preinstalled `ato_core`, and must prove that a second command reuses the managed runtime.

Generated `vendor/`, `release-artifacts/`, Python distributions, npm tarballs, and release manifests are never committed. Release packages must be built once and published from the exact verified bytes in dependency order: shared, CLI, MCP, then root.

## Pull requests

- Keep commits scoped and explain user-visible behavior.
- Add tests for success, failure, and permission-sensitive paths.
- Update user docs when commands, setup, bridge schemas, or task behavior changes.
- Do not commit local task output, secrets, coverage output, wheels, or tarballs.
- Run `git diff --check` and `pnpm run verify` before requesting review.
