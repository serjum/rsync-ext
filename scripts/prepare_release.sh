#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RELEASE_TYPE="${RELEASE_TYPE:-}"
DRY_RUN="${DRY_RUN:-0}"

cd "${ROOT_DIR}"

current_version="$(
  "${PYTHON_BIN}" - <<'PY'
import tomllib
from pathlib import Path

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
)"

if [ -z "${RELEASE_TYPE}" ]; then
  printf 'Current version: %s\n' "${current_version}"
  read -r -p "Release type [patch/minor/major/current] (default: current): " RELEASE_TYPE
fi

RELEASE_TYPE="${RELEASE_TYPE:-current}"

case "${RELEASE_TYPE}" in
  patch|minor|major|current)
    ;;
  *)
    echo "Invalid release type: ${RELEASE_TYPE}" >&2
    echo "Expected one of: patch, minor, major, current" >&2
    exit 1
    ;;
esac

if [ -n "$(git status --porcelain)" ]; then
  echo "Git working tree must be clean before running make release." >&2
  exit 1
fi

run_cmd() {
  if [ "${DRY_RUN}" = "1" ]; then
    printf '+'
    for arg in "$@"; do
      printf ' %q' "${arg}"
    done
    printf '\n'
  else
    "$@"
  fi
}

new_version="${current_version}"

if [ "${RELEASE_TYPE}" != "current" ]; then
  new_version="$("${PYTHON_BIN}" scripts/bump_version.py "${RELEASE_TYPE}")"
  run_cmd git add pyproject.toml src/rsync_ext/__init__.py
  run_cmd git commit -m "Release v${new_version}"
fi

tag="v${new_version}"

if git rev-parse "${tag}" >/dev/null 2>&1; then
  echo "Tag ${tag} already exists." >&2
  exit 1
fi

run_cmd ./scripts/build-deb.sh
run_cmd git tag -a "${tag}" -m "Release ${tag}"

printf 'Prepared release %s\n' "${tag}"
printf 'Push it with: git push origin HEAD --follow-tags\n'
