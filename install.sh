#!/usr/bin/env bash

set -euo pipefail

REPO_URL="https://github.com/duanluan/openai-local-bridge"
PACKAGE_REF="git+${REPO_URL}.git"

log() {
  printf '%s\n' "$*"
}

ensure_python() {
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
    return
  fi
  log "missing command: python3 or python"
  exit 1
}

install_with_uv_tool() {
  uv tool install --refresh "$PACKAGE_REF"
}

install_with_pip() {
  "$PYTHON_BIN" -m pip install --user --upgrade "$PACKAGE_REF"
}

main() {
  if command -v uv >/dev/null 2>&1; then
    log "using uv tool install"
    install_with_uv_tool
    log "installed successfully, try: olb"
    exit 0
  fi

  ensure_python
  if "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    log "using pip --user install"
    install_with_pip
    log "installed successfully, ensure your user bin directory is in PATH, then run: olb"
    exit 0
  fi

  log "missing installer: uv or pip"
  exit 1
}

main "$@"
