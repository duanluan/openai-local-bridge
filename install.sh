#!/usr/bin/env bash

set -euo pipefail

REPO_URL="https://github.com/duanluan/openai-local-bridge"
PACKAGE_REF="git+${REPO_URL}.git"

log() {
  printf '%s\n' "$*"
}

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
    zh:missing_python) printf '缺少命令：python3 或 python' ;;
    zh:using_uv) printf '使用 uv tool install' ;;
    zh:installed_try_olb) printf '安装完成，试试：olb' ;;
    zh:using_pip) printf '使用 pip --user install' ;;
    zh:installed_user_bin) printf '安装完成，请确认用户 bin 目录已加入 PATH，然后执行：olb' ;;
    zh:missing_installer) printf '缺少安装器：uv 或 pip' ;;
    en:missing_python) printf 'missing command: python3 or python' ;;
    en:using_uv) printf 'using uv tool install' ;;
    en:installed_try_olb) printf 'installed successfully, try: olb' ;;
    en:using_pip) printf 'using pip --user install' ;;
    en:installed_user_bin) printf 'installed successfully, ensure your user bin directory is in PATH, then run: olb' ;;
    en:missing_installer) printf 'missing installer: uv or pip' ;;
  esac
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
  log "$(text missing_python)"
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
    log "$(text using_uv)"
    install_with_uv_tool
    log "$(text installed_try_olb)"
    exit 0
  fi

  ensure_python
  if "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    log "$(text using_pip)"
    install_with_pip
    log "$(text installed_user_bin)"
    exit 0
  fi

  log "$(text missing_installer)"
  exit 1
}

main "$@"
