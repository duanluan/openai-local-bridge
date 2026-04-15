#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

language() {
  local raw="${OLB_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}"
  case "${raw%%.*}" in
    zh*|ZH*)
      printf 'zh'
      ;;
    *)
      printf 'en'
      ;;
  esac
}

text() {
  local lang
  lang="$(language)"
  case "${lang}:$1" in
    zh:missing_runtime) printf '缺少命令：uv、python3 或 python' ;;
    en:missing_runtime) printf 'missing command: uv, python3, or python' ;;
  esac
}

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
    printf '%s\n' "$(text missing_runtime)" >&2
    exit 1
  fi

  (cd "${SCRIPT_DIR}" && exec "${python_bin}" -m olb_cli "$@")
}

run_cli "$@"
