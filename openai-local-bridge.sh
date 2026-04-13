#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_cli() {
  if command -v uv >/dev/null 2>&1; then
    (cd "${SCRIPT_DIR}" && exec uv run olb "$@")
  fi

  local python_bin=""
  if command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
  elif command -v python >/dev/null 2>&1; then
    python_bin="python"
  else
    printf 'missing command: uv, python3, or python\n' >&2
    exit 1
  fi

  (cd "${SCRIPT_DIR}" && exec "${python_bin}" -m olb_cli "$@")
}

run_cli "$@"
