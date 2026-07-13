#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
artifacts="$temp/artifacts"
python_artifacts="$artifacts/python"
npm_artifacts="$artifacts/npm"
trap 'rm -rf "$temp"' EXIT

mkdir -p "$python_artifacts" "$npm_artifacts"
cd "$repo"
python -m build packages/core --outdir "$python_artifacts"
pnpm run build
(cd packages/shared && pnpm pack --pack-destination "$npm_artifacts")
(cd packages/cli && pnpm pack --pack-destination "$npm_artifacts")
(cd packages/mcp-server && pnpm pack --pack-destination "$npm_artifacts")
pnpm pack --pack-destination "$npm_artifacts"

wheels=("$python_artifacts"/*.whl)
tarballs=("$npm_artifacts"/*.tgz)
[[ ${#wheels[@]} -eq 1 ]] || { echo "Expected one wheel, found ${#wheels[@]}" >&2; exit 1; }
[[ ${#tarballs[@]} -eq 4 ]] || { echo "Expected four npm tarballs, found ${#tarballs[@]}" >&2; exit 1; }

python -m venv "$temp/venv"
venv_python="$temp/venv/bin/python"
"$venv_python" -m pip install --disable-pip-version-check "${wheels[0]}"

mkdir "$temp/npm-project"
cd "$temp/npm-project"
npm init -y >/dev/null
npm install --ignore-scripts "${tarballs[@]}"
export ATO_PYTHON="$venv_python"
./node_modules/.bin/ato --version
./node_modules/.bin/ato doctor
./node_modules/.bin/ato roles
"$venv_python" -c "import ato_core; from ato_core.models.role import RoleLoader; assert 'architect' in RoleLoader().list_roles(); print(ato_core.__version__)"
node "$repo/scripts/e2e/mcp-smoke.mjs" "$temp/npm-project/node_modules/@spacesky-cell/agent-team-orchestrator/bin/ato-mcp.js"
echo "Cold installation passed"
