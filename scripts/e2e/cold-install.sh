#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
artifacts="$temp/artifacts"
python_artifacts="$artifacts/python"
npm_artifacts="$artifacts/npm"
vendor="$repo/vendor"
vendor_created=0

cleanup() {
  if [[ "$vendor_created" == 1 ]]; then rm -rf -- "$vendor"; fi
  rm -rf -- "$temp"
}
trap cleanup EXIT

[[ ! -e "$vendor" ]] || { echo "Refusing to overwrite existing generated vendor directory: $vendor" >&2; exit 1; }
mkdir -p "$python_artifacts" "$npm_artifacts"
cd "$repo"
python -m build packages/core --outdir "$python_artifacts"
node scripts/release/prepare-npm-runtime.mjs "$python_artifacts" "$vendor"
vendor_created=1
pnpm run build
(cd packages/shared && pnpm pack --pack-destination "$npm_artifacts")
(cd packages/cli && pnpm pack --pack-destination "$npm_artifacts")
(cd packages/mcp-server && pnpm pack --pack-destination "$npm_artifacts")
pnpm pack --pack-destination "$npm_artifacts"

mapfile -t tarballs < <(find "$npm_artifacts" -maxdepth 1 -type f -name '*.tgz' -print | sort)
[[ ${#tarballs[@]} -eq 4 ]] || { echo "Expected four npm tarballs, found ${#tarballs[@]}" >&2; exit 1; }
root_tarball=""
for tarball in "${tarballs[@]}"; do
  package_json="$(tar -xOf "$tarball" package/package.json)"
  [[ "$package_json" != *"workspace:"* ]] || { echo "$(basename "$tarball") contains workspace dependency" >&2; exit 1; }
  package_name="$(printf '%s' "$package_json" | node -e 'let value=""; process.stdin.on("data", chunk => value += chunk); process.stdin.on("end", () => console.log(JSON.parse(value).name));')"
  if [[ "$package_name" == "@spacesky-cell/agent-team-orchestrator" ]]; then root_tarball="$tarball"; fi
done
[[ -n "$root_tarball" ]] || { echo "Root npm tarball was not produced" >&2; exit 1; }
root_files="$(tar -tf "$root_tarball")"
grep -Fxq 'package/vendor/ato-core.whl' <<<"$root_files"
grep -Fxq 'package/vendor/runtime-manifest.json' <<<"$root_files"

python -m venv "$temp/clean-base-python"
clean_python="$temp/clean-base-python/bin/python"
export PATH="$temp/clean-base-python/bin:$PATH"
export PYTHONNOUSERSITE=1
unset ATO_PYTHON ATO_BUNDLED_RUNTIME_MANIFEST || true
"$clean_python" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('ato_core') is None else 1)"

mkdir "$temp/npm-project"
cd "$temp/npm-project"
npm init -y >/dev/null
npm install --ignore-scripts "${tarballs[@]}"
export ATO_HOME="$temp/ato-home"
expected_version="$(node -p "require('$repo/package.json').version")"
version="$(./node_modules/.bin/ato --version)"
[[ "$version" == "$expected_version" ]] || { echo "Expected ato $expected_version, received $version" >&2; exit 1; }
[[ ! -e "$ATO_HOME/runtime" ]] || { echo "ato --version created the managed runtime" >&2; exit 1; }

doctor_json="$(./node_modules/.bin/ato doctor 2>"$temp/first-doctor.stderr")"
core_version="$(printf '%s' "$doctor_json" | "$clean_python" -c 'import json,sys; print(json.load(sys.stdin)["core_version"])')"
managed_python="$(printf '%s' "$doctor_json" | "$clean_python" -c 'import json,sys; print(json.load(sys.stdin)["python"])')"
[[ "$core_version" == "$expected_version" ]] || { echo "Managed core version $core_version differs from $expected_version" >&2; exit 1; }
"$clean_python" -c 'import os,sys; root=os.path.realpath(sys.argv[1]); selected=os.path.realpath(sys.argv[2]); raise SystemExit(0 if os.path.commonpath([root, selected]) == root else 1)' "$ATO_HOME/runtime" "$managed_python"
grep -q 'Installing bundled ATO core' "$temp/first-doctor.stderr"
./node_modules/.bin/ato roles >/dev/null

second_doctor="$(./node_modules/.bin/ato doctor 2>"$temp/second-doctor.stderr")"
second_python="$(printf '%s' "$second_doctor" | "$clean_python" -c 'import json,sys; print(json.load(sys.stdin)["python"])')"
[[ "$second_python" == "$managed_python" ]] || { echo "Second doctor selected a different runtime" >&2; exit 1; }
! grep -Eq 'Creating an isolated|Installing bundled' "$temp/second-doctor.stderr"

mcp_entry="$temp/npm-project/node_modules/@spacesky-cell/agent-team-orchestrator/bin/ato-mcp.js"
node "$repo/scripts/e2e/mcp-smoke.mjs" "$mcp_entry"
export ATO_BUNDLED_RUNTIME_MANIFEST="$temp/missing-runtime-manifest.json"
node "$repo/scripts/e2e/mcp-smoke.mjs" "$mcp_entry" --expect-failure BUNDLED_RUNTIME_INVALID
echo "npm-only cold installation passed"
