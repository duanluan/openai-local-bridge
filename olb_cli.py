#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from olb_i18n import (
    SUPPORTED_LANGUAGES,
    apply_language_override,
    install_argparse_i18n,
    t,
    translate_field_label,
    translate_status_label,
    translate_status_value,
)
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table


APP_SLUG = "openai-local-bridge"
APP_TITLE = "OpenAI Local Bridge"
INTERNAL_BRIDGE_COMMAND = "__bridge_internal__"
DEFAULT_TARGET_HOST = "api.openai.com"
DEFAULT_HOSTS_IP = "127.0.0.1"
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = "443"
DEFAULT_REASONING_EFFORT = "medium"
DEFAULT_REASONING_FORMAT = "openai"
DEFAULT_ACCOUNT_NAME = "default"
DEFAULT_BACKGROUND_LOG_MAX_BYTES = "1048576"
DEFAULT_BACKGROUND_LOG_BACKUP_COUNT = "3"
PYINSTALLER_RESET_ENVIRONMENT = "PYINSTALLER_RESET_ENVIRONMENT"
HOSTS_BEGIN = f"# BEGIN {APP_SLUG}"
HOSTS_END = f"# END {APP_SLUG}"
ROOT_CA_NAME = f"{APP_SLUG}-root-ca"
BAD_MODEL_VALUES = {"your-model-id", "你的上游模型ID", "your_model_id"}
REASONING_EFFORT_CHOICES = ["minimal", "low", "medium", "high", "xhigh"]
ACCOUNT_FIELDS = (
    "upstream_base",
    "upstream_key",
    "reasoning_effort",
    "reasoning_effort_format",
    "upstream_model",
    "model_map",
    "exposed_models",
    "force_stream_mode",
    "upstream_insecure",
    "debug",
)
REQUIRED_ACCOUNT_FIELDS = ("upstream_base", "upstream_key", "reasoning_effort")
WINDOWS_ERROR_ACCESS_DENIED = 5
WINDOWS_ERROR_INVALID_PARAMETER = 87
WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WINDOWS_STILL_ACTIVE = 259

console = Console()


class CliError(RuntimeError):
    pass


@dataclass
class AppPaths:
    root: Path
    config_file: Path
    cert_dir: Path
    root_ca_key: Path
    root_ca_cert: Path
    root_ca_srl: Path
    nss_db_dir: Path

    def domain_key(self, domain: str) -> Path:
        return self.cert_dir / f"{domain}.key"

    def domain_csr(self, domain: str) -> Path:
        return self.cert_dir / f"{domain}.csr"

    def domain_crt(self, domain: str) -> Path:
        return self.cert_dir / f"{domain}.crt"

    def domain_ext(self, domain: str) -> Path:
        return self.cert_dir / f"{domain}.ext.cnf"


def app_version() -> str:
    try:
        return package_version(APP_SLUG)
    except PackageNotFoundError:
        return "0.3.1"


def detect_os() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def get_paths() -> AppPaths:
    system = detect_os()
    if system == "windows":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_SLUG
    else:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        root = config_home / APP_SLUG

    cert_dir = root / "ca"
    return AppPaths(
        root=root,
        config_file=root / "config.json",
        cert_dir=cert_dir,
        root_ca_key=cert_dir / f"{ROOT_CA_NAME}.key",
        root_ca_cert=cert_dir / f"{ROOT_CA_NAME}.crt",
        root_ca_srl=cert_dir / f"{ROOT_CA_NAME}.srl",
        nss_db_dir=Path.home() / ".pki" / "nssdb",
    )


def bridge_pid_file(paths: AppPaths) -> Path:
    return paths.root / "bridge.pid"


def bridge_log_file(paths: AppPaths) -> Path:
    return paths.root / "bridge.log"


def bridge_mode_file(paths: AppPaths) -> Path:
    return paths.root / "bridge.mode"


def read_pid_file(path: Path) -> int | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        path.unlink(missing_ok=True)
        return None
    try:
        pid = int(raw)
    except ValueError:
        path.unlink(missing_ok=True)
        return None
    return pid if pid > 0 else None


def windows_kernel32() -> Any:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    return kernel32


def windows_last_error() -> int:
    getter = getattr(ctypes, "get_last_error", None)
    return getter() if getter is not None else 0


def windows_process_exists(pid: int) -> bool:
    kernel32 = windows_kernel32()
    handle = kernel32.OpenProcess(WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        error = windows_last_error()
        if error == WINDOWS_ERROR_ACCESS_DENIED:
            return True
        if error == WINDOWS_ERROR_INVALID_PARAMETER:
            return False
        raise OSError(error, f"OpenProcess failed with winerror {error}")
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            error = windows_last_error()
            if error == WINDOWS_ERROR_ACCESS_DENIED:
                return True
            raise OSError(error, f"GetExitCodeProcess failed with winerror {error}")
        return exit_code.value == WINDOWS_STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def read_mode_file(path: Path) -> str | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip().lower()
    if raw in {"background", "debug"}:
        return raw
    path.unlink(missing_ok=True)
    return None


def write_mode_file(path: Path, *, background: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("background\n" if background else "debug\n", encoding="utf-8")


def process_exists(pid: int) -> bool:
    if detect_os() == "windows":
        return windows_process_exists(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def running_bridge_pid(paths: AppPaths) -> int | None:
    pid_path = bridge_pid_file(paths)
    pid = read_pid_file(pid_path)
    if pid is None:
        return None
    if process_exists(pid):
        return pid
    pid_path.unlink(missing_ok=True)
    bridge_mode_file(paths).unlink(missing_ok=True)
    return None


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def require_command(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    if name == "openssl" and detect_os() == "windows":
        raise CliError(t("missing_command_openssl_windows"))
    raise CliError(t("missing_command", name=name))


def run_command(
    command: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=check,
            text=True,
            capture_output=capture_output,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr or exc.stdout or ""
        detail = detail.strip()
        if detail:
            raise CliError(detail) from exc
        raise CliError(t("command_failed", command=" ".join(command))) from exc
    except FileNotFoundError as exc:
        try:
            require_command(command[0])
        except CliError as missing:
            raise missing from exc
        raise CliError(t("missing_command", name=command[0])) from exc


def run_privileged(command: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    if detect_os() == "windows":
        return run_command(command, capture_output=capture_output)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return run_command(command, capture_output=capture_output)
    require_command("sudo")
    return run_command(["sudo", *command], capture_output=capture_output)


def normalize_account_name(raw: Any) -> str:
    return str(raw).strip() if raw is not None else ""


def extract_account_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {key: raw.get(key) for key in ACCOUNT_FIELDS if key in raw}


def has_account_config(raw: dict[str, Any]) -> bool:
    return any(key in raw for key in ACCOUNT_FIELDS)


def normalize_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    accounts_raw = raw.get("accounts")
    if isinstance(accounts_raw, dict):
        accounts: dict[str, dict[str, Any]] = {}
        for name, account_raw in accounts_raw.items():
            account_name = normalize_account_name(name)
            if not account_name:
                continue
            accounts[account_name] = extract_account_config(account_raw)
        active_name = normalize_account_name(raw.get("active_account"))
        if active_name not in accounts and accounts:
            active_name = next(iter(accounts))
        return {"active_account": active_name, "accounts": accounts}

    if not has_account_config(raw):
        return {}

    return {
        "active_account": DEFAULT_ACCOUNT_NAME,
        "accounts": {
            DEFAULT_ACCOUNT_NAME: extract_account_config(raw),
        },
    }


def accounts_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    accounts = config.get("accounts", {})
    return accounts if isinstance(accounts, dict) else {}


def account_names(config: dict[str, Any]) -> list[str]:
    return list(accounts_map(config).keys())


def active_account_name(config: dict[str, Any]) -> str:
    accounts = accounts_map(config)
    active_name = normalize_account_name(config.get("active_account"))
    if active_name in accounts:
        return active_name
    if accounts:
        return next(iter(accounts))
    return ""


def account_config(config: dict[str, Any], name: str) -> dict[str, Any]:
    return dict(accounts_map(config).get(name, {}))


def active_account_config(config: dict[str, Any]) -> dict[str, Any]:
    current_name = active_account_name(config)
    if not current_name:
        return {}
    return account_config(config, current_name)


def require_account_name(name: str) -> str:
    account_name = normalize_account_name(name)
    if not account_name:
        raise CliError(t("account_name_required"))
    return account_name


def require_accounts(paths: AppPaths, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    accounts = accounts_map(config)
    if accounts:
        return accounts
    if paths.config_file.exists():
        raise CliError(t("accounts_empty"))
    raise CliError(t("config_missing", path=paths.config_file))


def require_existing_account(paths: AppPaths, config: dict[str, Any], name: str) -> str:
    account_name = require_account_name(name)
    if account_name not in require_accounts(paths, config):
        raise CliError(t("account_not_found", name=account_name))
    return account_name


def upsert_account(config: dict[str, Any], name: str, account: dict[str, Any], *, activate: bool = False) -> dict[str, Any]:
    store = normalize_config(config)
    accounts = dict(accounts_map(store))
    accounts[name] = account
    active_name = active_account_name(store)
    if activate or not active_name:
        active_name = name
    elif active_name not in accounts:
        active_name = next(iter(accounts))
    return {"active_account": active_name, "accounts": accounts}


def switch_account(config: dict[str, Any], name: str) -> dict[str, Any]:
    store = normalize_config(config)
    return {"active_account": name, "accounts": dict(accounts_map(store))}


def delete_account(config: dict[str, Any], name: str) -> dict[str, Any]:
    store = normalize_config(config)
    accounts = dict(accounts_map(store))
    accounts.pop(name, None)
    active_name = active_account_name(store)
    if active_name == name or active_name not in accounts:
        active_name = next(iter(accounts), "")
    return {"active_account": active_name, "accounts": accounts}


def has_required_account_values(config: dict[str, Any]) -> bool:
    return all(str(config.get(key, "")).strip() for key in REQUIRED_ACCOUNT_FIELDS)


def load_config(paths: AppPaths) -> dict[str, Any]:
    if not paths.config_file.exists():
        return {}
    return normalize_config(json.loads(paths.config_file.read_text(encoding="utf-8")))


def save_config(paths: AppPaths, config: dict[str, Any]) -> None:
    normalized = normalize_config(config)
    if not accounts_map(normalized):
        paths.config_file.unlink(missing_ok=True)
        return
    payload = {
        "active_account": active_account_name(normalized),
        "accounts": accounts_map(normalized),
    }
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_target_host() -> str:
    return os.environ.get("OLB_TARGET_HOST", DEFAULT_TARGET_HOST)


def get_hosts_ip() -> str:
    return os.environ.get("OLB_HOSTS_IP", DEFAULT_HOSTS_IP)


def get_optional_env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "")
    return value if value else default


def reasoning_effort_choices(default_effort: str) -> list[str]:
    effort = default_effort.strip()
    choices = list(REASONING_EFFORT_CHOICES)
    if effort and effort not in choices:
        choices.append(effort)
    return choices


def prompt_reasoning_effort(default_effort: str) -> str:
    return Prompt.ask(
        t("reasoning_effort_label"),
        choices=reasoning_effort_choices(default_effort),
        default=default_effort,
    ).strip()


def should_elevate_for_listener(listen_port: str | int) -> bool:
    if detect_os() == "windows":
        return False
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return False
    return 0 < int(str(listen_port).strip()) < 1024


def preserved_env_names(env: dict[str, str]) -> str:
    names = {name for name in env if name.startswith("OLB_")}
    if PYINSTALLER_RESET_ENVIRONMENT in env:
        names.add(PYINSTALLER_RESET_ENVIRONMENT)
    return ",".join(sorted(names))


def cli_entry_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "olb_cli"]


def run_embedded_bridge(argv: list[str]) -> int:
    import openai_local_bridge

    return openai_local_bridge.main(argv)


def build_proxy_command(
    domain_crt: Path,
    domain_key: Path,
    env: dict[str, str],
    *,
    pid_file: Path | None = None,
) -> list[str]:
    command = [
        *cli_entry_command(),
        INTERNAL_BRIDGE_COMMAND,
        "--cert",
        str(domain_crt),
        "--key",
        str(domain_key),
    ]
    if pid_file is not None:
        command.extend(["--pid-file", str(pid_file)])
    if not should_elevate_for_listener(env.get("OLB_LISTEN_PORT", DEFAULT_LISTEN_PORT)):
        return command

    require_command("sudo")
    preserved = preserved_env_names(env)
    if preserved:
        return ["sudo", f"--preserve-env={preserved}", *command]
    return ["sudo", *command]


def env_from_config(config: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    mapping = {
        "OLB_UPSTREAM_BASE": config.get("upstream_base", ""),
        "OLB_UPSTREAM_KEY": config.get("upstream_key", ""),
        "OLB_REASONING_EFFORT": config.get("reasoning_effort", ""),
        "OLB_REASONING_EFFORT_FORMAT": config.get("reasoning_effort_format", DEFAULT_REASONING_FORMAT),
        "OLB_UPSTREAM_MODEL": config.get("upstream_model", ""),
        "OLB_MODEL_MAP_JSON": json.dumps(config.get("model_map", {}), ensure_ascii=False),
        "OLB_EXPOSED_MODELS_JSON": json.dumps(config.get("exposed_models", []), ensure_ascii=False),
        "OLB_FORCE_STREAM_MODE": "" if config.get("force_stream_mode") is None else str(config.get("force_stream_mode")).lower(),
        "OLB_UPSTREAM_INSECURE": str(bool(config.get("upstream_insecure", False))).lower(),
        "OLB_DEBUG": str(bool(config.get("debug", True))).lower(),
    }
    env.update(mapping)
    env.setdefault("OLB_TARGET_HOST", get_target_host())
    env.setdefault("OLB_HOSTS_IP", get_hosts_ip())
    env.setdefault("OLB_LISTEN_HOST", get_optional_env("OLB_LISTEN_HOST", DEFAULT_LISTEN_HOST))
    env.setdefault("OLB_LISTEN_PORT", get_optional_env("OLB_LISTEN_PORT", DEFAULT_LISTEN_PORT))
    return env


def validate_upstream(config: dict[str, Any]) -> None:
    target = get_target_host()
    upstream = str(config.get("upstream_base", "")).rstrip("/")
    if not upstream:
        raise CliError(t("upstream_base_required"))

    parsed = urlparse(upstream)
    if not parsed.scheme or not parsed.netloc:
        raise CliError(t("invalid_upstream_base"))
    if parsed.hostname == target:
        raise CliError(t("upstream_base_host_conflict"))

    upstream_model = str(config.get("upstream_model", "")).strip()
    if upstream_model in BAD_MODEL_VALUES:
        raise CliError(t("replace_upstream_model_placeholder"))

    model_map_raw = json.dumps(config.get("model_map", {}), ensure_ascii=False).lower()
    if "your-model-id" in model_map_raw or "你的上游模型id" in model_map_raw:
        raise CliError(t("replace_model_map_placeholder"))


def prompt_for_config(existing: dict[str, Any], *, intro_key: str = "config_intro_init") -> dict[str, Any]:
    console.print(Panel.fit(t(intro_key), title=APP_TITLE))

    old_base = str(existing.get("upstream_base", "")).strip()
    if old_base:
        base_prompt = t("base_prompt_saved")
        default_base = old_base
    else:
        base_prompt = t("base_prompt_default")
        default_base = "https://your-openai-compatible.example/v1"
    base_url = Prompt.ask(base_prompt, default=default_base).strip()

    old_key = str(existing.get("upstream_key", ""))
    if old_key:
        entered_key = Prompt.ask(t("api_key_keep", masked=mask_secret(old_key)), default="").strip()
        api_key = entered_key or old_key
    else:
        api_key = Prompt.ask(t("api_key_prompt")).strip()

    old_effort = str(existing.get("reasoning_effort", "")).strip()
    default_effort = old_effort or DEFAULT_REASONING_EFFORT
    if old_effort:
        reasoning_prompt = t("reasoning_prompt_saved")
    else:
        reasoning_prompt = t("reasoning_prompt_default")
    reasoning_effort = Prompt.ask(
        reasoning_prompt,
        choices=reasoning_effort_choices(default_effort),
        default=default_effort,
    ).strip()

    config = {
        "upstream_base": base_url.rstrip("/"),
        "upstream_key": api_key,
        "reasoning_effort": reasoning_effort,
        "reasoning_effort_format": str(existing.get("reasoning_effort_format", DEFAULT_REASONING_FORMAT)),
        "upstream_model": str(existing.get("upstream_model", "")).strip(),
        "model_map": existing.get("model_map", {}),
        "exposed_models": existing.get("exposed_models", []),
        "force_stream_mode": existing.get("force_stream_mode"),
        "upstream_insecure": bool(existing.get("upstream_insecure", False)),
        "debug": bool(existing.get("debug", True)),
    }

    validate_upstream(config)
    if not config["upstream_key"]:
        raise CliError(t("upstream_key_required"))
    return config


def ensure_config(paths: AppPaths, *, interactive: bool) -> dict[str, Any]:
    store = load_config(paths)
    current_name = active_account_name(store) or DEFAULT_ACCOUNT_NAME
    config = active_account_config(store)
    if has_required_account_values(config):
        validate_upstream(config)
        return config
    if not interactive:
        raise CliError(t("missing_config", path=paths.config_file))
    config = prompt_for_config(config)
    save_config(paths, upsert_account(store, current_name, config, activate=True))
    console.print(t("config_saved", path=paths.config_file))
    return config


def ensure_root_ca(paths: AppPaths) -> None:
    require_command("openssl")
    paths.cert_dir.mkdir(parents=True, exist_ok=True)
    if paths.root_ca_key.exists() and paths.root_ca_cert.exists():
        return
    run_command(["openssl", "genrsa", "-out", str(paths.root_ca_key), "2048"])
    run_command(
        [
            "openssl",
            "req",
            "-x509",
            "-new",
            "-nodes",
            "-key",
            str(paths.root_ca_key),
            "-sha256",
            "-days",
            "3650",
            "-subj",
            "/CN=OpenAI Local Bridge Root CA",
            "-out",
            str(paths.root_ca_cert),
        ]
    )


def ensure_domain_cert(paths: AppPaths) -> tuple[Path, Path]:
    domain = get_target_host()
    domain_key = paths.domain_key(domain)
    domain_csr = paths.domain_csr(domain)
    domain_crt = paths.domain_crt(domain)
    domain_ext = paths.domain_ext(domain)

    ensure_root_ca(paths)
    if domain_key.exists() and domain_crt.exists():
        return domain_crt, domain_key

    require_command("openssl")
    paths.cert_dir.mkdir(parents=True, exist_ok=True)
    run_command(["openssl", "genrsa", "-out", str(domain_key), "2048"])
    run_command(["openssl", "req", "-new", "-key", str(domain_key), "-subj", f"/CN={domain}", "-out", str(domain_csr)])
    domain_ext.write_text(
        "\n".join(
            [
                f"subjectAltName=DNS:{domain}",
                "extendedKeyUsage=serverAuth",
                "keyUsage=digitalSignature,keyEncipherment",
                "basicConstraints=CA:FALSE",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_command(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(domain_csr),
            "-CA",
            str(paths.root_ca_cert),
            "-CAkey",
            str(paths.root_ca_key),
            "-CAcreateserial",
            "-out",
            str(domain_crt),
            "-days",
            "825",
            "-sha256",
            "-extfile",
            str(domain_ext),
        ]
    )
    return domain_crt, domain_key


def detect_ca_strategy() -> str:
    system = detect_os()
    if system == "macos" and shutil.which("security"):
        return "security"
    if shutil.which("trust"):
        return "trust"
    if shutil.which("update-ca-certificates"):
        return "update-ca-certificates"
    if shutil.which("update-ca-trust"):
        return "update-ca-trust"
    return "manual"


def install_ca(paths: AppPaths) -> None:
    ensure_root_ca(paths)
    system = detect_os()

    if system == "windows":
        require_command("certutil")
        run_command(["certutil", "-user", "-addstore", "Root", str(paths.root_ca_cert)])
        console.print(t("root_ca_imported_windows"))
        return

    strategy = detect_ca_strategy()
    if strategy == "security":
        run_privileged([
            "security",
            "add-trusted-cert",
            "-d",
            "-r",
            "trustRoot",
            "-k",
            "/Library/Keychains/System.keychain",
            str(paths.root_ca_cert),
        ])
        console.print(t("root_ca_imported_macos"))
        return

    if strategy == "trust":
        run_privileged(["trust", "anchor", str(paths.root_ca_cert)])
        if shutil.which("update-ca-certificates"):
            run_privileged(["update-ca-certificates"])
        elif shutil.which("update-ca-trust"):
            run_privileged(["update-ca-trust", "extract"])
        else:
            run_privileged(["trust", "extract-compat"])
        console.print(t("root_ca_imported_trust"))
        return

    if strategy == "update-ca-certificates":
        anchor_dir = Path("/usr/local/share/ca-certificates")
        anchor_file = anchor_dir / f"{ROOT_CA_NAME}.crt"
        run_privileged(["install", "-d", "-m", "0755", str(anchor_dir)])
        run_privileged(["install", "-m", "0644", str(paths.root_ca_cert), str(anchor_file)])
        run_privileged(["update-ca-certificates"])
        console.print(t("root_ca_written", path=anchor_file))
        return

    if strategy == "update-ca-trust":
        anchor_dir = Path("/etc/pki/ca-trust/source/anchors")
        anchor_file = anchor_dir / f"{ROOT_CA_NAME}.crt"
        run_privileged(["install", "-d", "-m", "0755", str(anchor_dir)])
        run_privileged(["install", "-m", "0644", str(paths.root_ca_cert), str(anchor_file)])
        run_privileged(["update-ca-trust", "extract"])
        console.print(t("root_ca_written", path=anchor_file))
        return

    raise CliError(t("auto_ca_unsupported"))


def install_nss(paths: AppPaths) -> None:
    system = detect_os()
    if system in {"windows", "macos"}:
        console.print(t("nss_not_needed"))
        return

    require_command("certutil")
    ensure_root_ca(paths)
    nss_db = f"sql:{paths.nss_db_dir}"
    paths.nss_db_dir.mkdir(parents=True, exist_ok=True)

    if not (paths.nss_db_dir / "cert9.db").exists():
        run_command(["certutil", "-d", nss_db, "-N", "--empty-password"])

    run_command(["certutil", "-d", nss_db, "-D", "-n", APP_SLUG], check=False, capture_output=True)
    run_command(["certutil", "-d", nss_db, "-A", "-t", "C,,", "-n", APP_SLUG, "-i", str(paths.root_ca_cert)])
    console.print(t("nss_imported", path=nss_db))


def get_hosts_file() -> Path:
    if detect_os() == "windows":
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        return system_root / "System32" / "drivers" / "etc" / "hosts"
    return Path("/etc/hosts")


def strip_hosts_entries(content: str) -> str:
    domain = get_target_host()
    ip = get_hosts_ip()
    lines = content.splitlines()
    result: list[str] = []
    skip = False

    for line in lines:
        stripped = line.strip()
        if stripped == HOSTS_BEGIN:
            skip = True
            continue
        if stripped == HOSTS_END:
            skip = False
            continue
        if skip:
            continue

        parts = stripped.split()
        if len(parts) >= 2 and parts[0] == ip and parts[1] == domain:
            continue
        result.append(line)

    rebuilt = "\n".join(result).rstrip("\n")
    if rebuilt:
        rebuilt += "\n"
    return rebuilt


def write_hosts(content: str) -> None:
    hosts_file = get_hosts_file()
    if detect_os() == "windows":
        hosts_file.write_text(content, encoding="utf-8")
        return

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        tmp.write(content)
        temp_path = Path(tmp.name)
    try:
        run_privileged(["cp", str(temp_path), str(hosts_file)])
    finally:
        temp_path.unlink(missing_ok=True)


def install_hosts() -> None:
    hosts_file = get_hosts_file()
    existing = hosts_file.read_text(encoding="utf-8") if hosts_file.exists() else ""
    cleaned = strip_hosts_entries(existing)
    block = "\n".join([HOSTS_BEGIN, f"{get_hosts_ip()} {get_target_host()}", HOSTS_END]) + "\n"
    write_hosts(cleaned + block)
    console.print(t("hosts_written", path=hosts_file))


def remove_hosts() -> None:
    hosts_file = get_hosts_file()
    existing = hosts_file.read_text(encoding="utf-8") if hosts_file.exists() else ""
    cleaned = strip_hosts_entries(existing)
    write_hosts(cleaned)
    console.print(t("hosts_removed", path=hosts_file))


def listener_state(listen_host: str, listen_port: int) -> str:
    sock = socket.socket()
    try:
        sock.settimeout(0.5)
        sock.connect((listen_host, listen_port))
        return "listening"
    except OSError:
        return "stopped"
    finally:
        sock.close()


def status_data(paths: AppPaths) -> dict[str, str]:
    domain = get_target_host()
    ip = get_hosts_ip()
    listen_host = get_optional_env("OLB_LISTEN_HOST", DEFAULT_LISTEN_HOST)
    listen_port = int(get_optional_env("OLB_LISTEN_PORT", DEFAULT_LISTEN_PORT))
    config = load_config(paths)
    hosts_file = get_hosts_file()
    hosts_state = "disabled"

    if hosts_file.exists():
        content = hosts_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0] == ip and parts[1] == domain:
                hosts_state = "enabled"
                break

    if detect_os() == "windows":
        ca_strategy = "certutil"
    else:
        ca_strategy = detect_ca_strategy()

    if detect_os() in {"macos", "windows"}:
        nss_state = "not_applicable"
        nss_db = "not_applicable"
    else:
        nss_db = f"sql:{paths.nss_db_dir}"
        if shutil.which("certutil") and (paths.nss_db_dir / "cert9.db").exists():
            result = run_command(["certutil", "-d", nss_db, "-L", "-n", APP_SLUG], check=False, capture_output=True)
            nss_state = "present" if result.returncode == 0 else "missing"
        else:
            nss_state = "unknown"

    return {
        "os": detect_os(),
        "target_host": domain,
        "hosts": hosts_state,
        "hosts_file": str(hosts_file),
        "root_ca": "present" if paths.root_ca_cert.exists() else "missing",
        "ca_install_strategy": ca_strategy,
        "nss": nss_state,
        "nss_db": nss_db,
        "listener": listener_state(listen_host, listen_port),
        "listen_addr": f"{listen_host}:{listen_port}",
        "active_account": active_account_name(config) or "not_configured",
        "config": str(paths.config_file),
    }


def print_status(paths: AppPaths) -> None:
    data = status_data(paths)
    table = Table(title=t("status_title"))
    table.add_column(t("table_item"))
    table.add_column(t("table_value"))
    for key, value in data.items():
        table.add_row(translate_status_label(key), translate_status_value(value))
    console.print(table)


def show_config(paths: AppPaths) -> None:
    store = load_config(paths)
    current_name = active_account_name(store)
    config = active_account_config(store)
    if not config:
        if paths.config_file.exists():
            console.print(t("accounts_empty"))
            return
        console.print(t("config_missing", path=paths.config_file))
        return
    table = Table(title=t("config_title"))
    table.add_column(t("table_item"))
    table.add_column(t("table_value"))
    table.add_row(translate_field_label("active_account"), current_name)
    table.add_row(translate_field_label("accounts"), ", ".join(account_names(store)))
    for key in ["upstream_base", "reasoning_effort", "reasoning_effort_format", "upstream_model"]:
        table.add_row(translate_field_label(key), str(config.get(key, "")))
    table.add_row(translate_field_label("upstream_key"), mask_secret(str(config.get("upstream_key", ""))))
    table.add_row(translate_field_label("config_path"), str(paths.config_file))
    console.print(table)


def show_accounts(paths: AppPaths) -> None:
    config = load_config(paths)
    accounts = require_accounts(paths, config)
    current_name = active_account_name(config)
    table = Table(title=t("accounts_title"))
    table.add_column(t("account_name_arg_help"))
    table.add_column(translate_field_label("active_account"))
    table.add_column(translate_field_label("upstream_base"))
    table.add_column(translate_field_label("reasoning_effort"))
    table.add_column(translate_field_label("upstream_key"))
    for name, account in accounts.items():
        table.add_row(
            name,
            "*" if name == current_name else "",
            str(account.get("upstream_base", "")),
            str(account.get("reasoning_effort", "")),
            mask_secret(str(account.get("upstream_key", ""))),
        )
    console.print(table)


def split_sudo_command(command: list[str]) -> tuple[list[str], list[str]]:
    if not command or command[0] != "sudo":
        raise ValueError(t("sudo_command_required"))
    index = 1
    while index < len(command) and command[index].startswith("-"):
        index += 1
    return command[:index], command[index:]


def prepare_background_launch(command: list[str]) -> None:
    if not command or command[0] != "sudo":
        return
    run_command(["sudo", "-v"])


def launch_background_with_sudo(command: list[str], env: dict[str, str], log_path: Path) -> None:
    sudo_prefix, inner_command = split_sudo_command(command)
    shell_command = f"nohup {shlex.join(inner_command)} >/dev/null 2>&1 </dev/null &"
    run_command(["sudo", "-n", *sudo_prefix[1:], "sh", "-c", shell_command], env=env)


def wait_for_background_start(paths: AppPaths, process: subprocess.Popen[str] | None, log_path: Path) -> int:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        pid = running_bridge_pid(paths)
        if pid is not None:
            console.print(t("bridge_running_background", pid=pid, log_path=log_path))
            return 0

        if process is not None:
            return_code = process.poll()
        else:
            return_code = None
        if return_code is not None:
            detail = ""
            if log_path.exists():
                lines = log_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
                if lines:
                    detail = lines[-1]
            if detail:
                raise CliError(t("bridge_start_failed_detail", detail=detail))
            raise CliError(t("bridge_start_failed_exit", code=return_code))

        time.sleep(0.2)

    raise CliError(t("bridge_start_timeout", log_path=log_path))


def stop_signal(pid: int) -> None:
    if detect_os() == "windows":
        os.kill(pid, signal.SIGTERM)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except PermissionError:
        run_privileged(["kill", "-TERM", str(pid)])


def force_stop_signal(pid: int) -> None:
    if detect_os() == "windows":
        os.kill(pid, signal.SIGTERM)
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except PermissionError:
        run_privileged(["kill", "-KILL", str(pid)])


def wait_for_process_exit(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return True
        time.sleep(0.2)
    return not process_exists(pid)


def start_proxy(paths: AppPaths, config: dict[str, Any], *, background: bool = False) -> int:
    existing_pid = running_bridge_pid(paths)
    if existing_pid is not None:
        raise CliError(t("bridge_already_running", pid=existing_pid))

    validate_upstream(config)
    domain_crt, domain_key = ensure_domain_cert(paths)
    env = env_from_config(config)
    listen_host = env.get("OLB_LISTEN_HOST", DEFAULT_LISTEN_HOST)
    listen_port = env.get("OLB_LISTEN_PORT", DEFAULT_LISTEN_PORT)
    pid_path = bridge_pid_file(paths)
    if background:
        paths.root.mkdir(parents=True, exist_ok=True)
        log_path = bridge_log_file(paths)
        env["OLB_LOG_PATH"] = str(log_path)
        env.setdefault("OLB_LOG_MAX_BYTES", DEFAULT_BACKGROUND_LOG_MAX_BYTES)
        env.setdefault("OLB_LOG_BACKUP_COUNT", DEFAULT_BACKGROUND_LOG_BACKUP_COUNT)
        if getattr(sys, "frozen", False):
            env[PYINSTALLER_RESET_ENVIRONMENT] = "1"
    command = build_proxy_command(domain_crt, domain_key, env, pid_file=pid_path)
    console.print(
        Panel.fit(
            t(
                "bridge_start_panel_body",
                target_host=get_target_host(),
                listen=f"{listen_host}:{listen_port}",
                upstream=config["upstream_base"],
                mode=t("mode_background") if background else t("mode_foreground"),
            ),
            title=t("bridge_start_panel_title"),
        )
    )

    if background:
        if command and command[0] == "sudo" and detect_os() != "windows":
            write_mode_file(bridge_mode_file(paths), background=True)
            prepare_background_launch(command)
            try:
                launch_background_with_sudo(command, env, log_path)
                return wait_for_background_start(paths, None, log_path)
            except Exception:
                bridge_mode_file(paths).unlink(missing_ok=True)
                raise
        popen_kwargs: dict[str, Any] = {
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if detect_os() == "windows":
            popen_kwargs["creationflags"] = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        else:
            popen_kwargs["start_new_session"] = True
        write_mode_file(bridge_mode_file(paths), background=True)
        try:
            process = subprocess.Popen(command, **popen_kwargs)
            return wait_for_background_start(paths, process, log_path)
        except Exception:
            bridge_mode_file(paths).unlink(missing_ok=True)
            raise

    write_mode_file(bridge_mode_file(paths), background=False)
    try:
        result = subprocess.run(command, env=env)
        return result.returncode
    finally:
        bridge_mode_file(paths).unlink(missing_ok=True)


def stop_proxy(paths: AppPaths) -> int:
    pid = running_bridge_pid(paths)
    if pid is None:
        console.print(t("bridge_not_running"))
        return 0

    stop_signal(pid)
    if not wait_for_process_exit(pid, 5):
        force_stop_signal(pid)
        if not wait_for_process_exit(pid, 2):
            raise CliError(t("cannot_stop_bridge", pid=pid))

    bridge_pid_file(paths).unlink(missing_ok=True)
    bridge_mode_file(paths).unlink(missing_ok=True)
    console.print(t("bridge_stopped", pid=pid))
    return 0


def follow_log_file(log_path: Path) -> None:
    handle = None
    position = 0
    file_key: tuple[int, int] | None = None
    initial_tail_shown = False

    try:
        while True:
            if not log_path.exists():
                time.sleep(0.2)
                continue

            stat = log_path.stat()
            current_key = (stat.st_dev, stat.st_ino)
            if handle is None or file_key != current_key or stat.st_size < position:
                if handle is not None:
                    handle.close()
                handle = log_path.open("r", encoding="utf-8", errors="ignore")
                if not initial_tail_shown:
                    lines = handle.readlines()
                    chunk = "".join(lines[-10:])
                    if chunk:
                        sys.stdout.write(chunk)
                        sys.stdout.flush()
                    position = handle.tell()
                    initial_tail_shown = True
                elif file_key != current_key or stat.st_size < position:
                    position = 0
                handle.seek(position)
                file_key = current_key

            chunk = handle.read()
            if chunk:
                sys.stdout.write(chunk)
                sys.stdout.flush()
                position = handle.tell()
                continue

            time.sleep(0.2)
    finally:
        if handle is not None:
            handle.close()


def run_init(paths: AppPaths) -> int:
    store = load_config(paths)
    current_name = active_account_name(store) or DEFAULT_ACCOUNT_NAME
    config = prompt_for_config(active_account_config(store), intro_key="config_intro_init")
    save_config(paths, upsert_account(store, current_name, config, activate=True))
    console.print(t("config_saved", path=paths.config_file))
    if Confirm.ask(t("show_config_after_init"), default=True):
        show_config(paths)
    return 0


def run_account_list(paths: AppPaths) -> int:
    show_accounts(paths)
    return 0


def run_account_add(paths: AppPaths, name: str) -> int:
    store = load_config(paths)
    account_name = require_account_name(name)
    if account_name in accounts_map(store):
        raise CliError(t("account_exists", name=account_name))
    config = prompt_for_config({}, intro_key="config_intro_add")
    save_config(paths, upsert_account(store, account_name, config, activate=not active_account_name(store)))
    console.print(t("account_added", name=account_name))
    return 0


def run_account_edit(paths: AppPaths, name: str | None = None) -> int:
    store = load_config(paths)
    accounts = require_accounts(paths, store)
    account_name = active_account_name(store) if name is None else require_account_name(name)
    if account_name not in accounts:
        raise CliError(t("account_not_found", name=account_name))
    config = prompt_for_config(account_config(store, account_name), intro_key="config_intro_edit")
    save_config(paths, upsert_account(store, account_name, config))
    console.print(t("account_updated", name=account_name))
    return 0


def run_account_delete(paths: AppPaths, name: str) -> int:
    store = load_config(paths)
    account_name = require_existing_account(paths, store, name)
    current_name = active_account_name(store)
    updated = delete_account(store, account_name)
    save_config(paths, updated)
    console.print(t("account_deleted", name=account_name))
    next_active = active_account_name(updated)
    if current_name == account_name and next_active:
        console.print(t("account_switched", name=next_active))
    return 0


def run_account_switch(paths: AppPaths, name: str) -> int:
    store = load_config(paths)
    account_name = require_existing_account(paths, store, name)
    updated = switch_account(store, account_name)
    save_config(paths, updated)
    console.print(t("account_switched", name=account_name))
    pid = running_bridge_pid(paths)
    if pid is not None and Confirm.ask(t("restart_bridge_after_account_switch", pid=pid, name=account_name), default=True):
        stop_proxy(paths)
        start_proxy(paths, account_config(updated, account_name), background=True)
    return 0


def run_enable(paths: AppPaths) -> int:
    install_ca(paths)
    install_nss(paths)
    install_hosts()
    return 0


def run_disable() -> int:
    remove_hosts()
    return 0


def run_start(paths: AppPaths, *, background: bool = True) -> int:
    if not paths.config_file.exists():
        console.print(t("missing_config_start_notice"))
    config = ensure_config(paths, interactive=True)
    run_enable(paths)
    return start_proxy(paths, config, background=background)


def run_stop(paths: AppPaths) -> int:
    return stop_proxy(paths)


def run_reload(paths: AppPaths, *, background: bool | None = None) -> int:
    if not paths.config_file.exists():
        console.print(t("missing_config_start_notice"))
    config = ensure_config(paths, interactive=True)
    run_enable(paths)
    pid = running_bridge_pid(paths)
    if background is None:
        if pid is None:
            background = True
        else:
            background = read_mode_file(bridge_mode_file(paths)) != "debug"
    if pid is not None:
        stop_proxy(paths)
    return start_proxy(paths, config, background=background)


def run_log(paths: AppPaths) -> int:
    log_path = bridge_log_file(paths)
    if not log_path.exists() and running_bridge_pid(paths) is None:
        raise CliError(t("bridge_log_missing", log_path=log_path))
    follow_log_file(log_path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    install_argparse_i18n()
    parser = argparse.ArgumentParser(prog="olb", description=t("cli_description"))
    parser.add_argument("--lang", choices=list(SUPPORTED_LANGUAGES), help=t("language_arg_help"))
    subparsers = parser.add_subparsers(dest="command", title=t("subcommands_title"))

    command_specs = [
        ("init", "cmd_init_help"),
        ("enable", "cmd_enable_help"),
        ("disable", "cmd_disable_help"),
        ("status", "cmd_status_help"),
        ("config", "cmd_config_help"),
        ("config-path", "cmd_config_path_help"),
        ("bootstrap-ca", "cmd_bootstrap_ca_help"),
        ("install-ca", "cmd_install_ca_help"),
        ("install-nss", "cmd_install_nss_help"),
        ("install-hosts", "cmd_install_hosts_help"),
        ("remove-hosts", "cmd_remove_hosts_help"),
        ("version", "cmd_version_help"),
        ("stop", "cmd_stop_help"),
        ("log", "cmd_log_help"),
    ]
    for name, help_key in command_specs:
        subparsers.add_parser(name, help=t(help_key), description=t(help_key))

    start_parser = subparsers.add_parser("start", help=t("cmd_start_help"), description=t("cmd_start_help"))
    start_parser.add_argument("--debug", action="store_true", help=t("start_debug_help"))

    reload_parser = subparsers.add_parser("reload", help=t("cmd_reload_help"), description=t("cmd_reload_help"))
    reload_parser.add_argument("--debug", action="store_true", help=t("start_debug_help"))

    account_parser = subparsers.add_parser(
        "account",
        aliases=["a"],
        help=t("cmd_account_help"),
        description=t("cmd_account_help"),
    )
    account_subparsers = account_parser.add_subparsers(dest="account_command", title=t("subcommands_title"))
    account_subparsers.add_parser(
        "list",
        aliases=["ls"],
        help=t("cmd_account_list_help"),
        description=t("cmd_account_list_help"),
    )

    add_parser = account_subparsers.add_parser("add", help=t("cmd_account_add_help"), description=t("cmd_account_add_help"))
    add_parser.add_argument("name", help=t("account_name_arg_help"))

    edit_parser = account_subparsers.add_parser(
        "edit",
        help=t("cmd_account_edit_help"),
        description=t("cmd_account_edit_help"),
    )
    edit_parser.add_argument("name", nargs="?", help=t("account_name_arg_help"))

    delete_parser = account_subparsers.add_parser(
        "delete",
        help=t("cmd_account_delete_help"),
        description=t("cmd_account_delete_help"),
    )
    delete_parser.add_argument("name", help=t("account_name_arg_help"))

    switch_parser = account_subparsers.add_parser(
        "use",
        aliases=["switch"],
        help=t("cmd_account_switch_help"),
        description=t("cmd_account_switch_help"),
    )
    switch_parser.add_argument("name", help=t("account_name_arg_help"))

    return parser


def default_command(paths: AppPaths) -> str:
    return "status" if paths.config_file.exists() else "init"


def safe_interrupt_notice(message: str) -> None:
    try:
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    apply_language_override(argv)
    if argv and argv[0] == INTERNAL_BRIDGE_COMMAND:
        return run_embedded_bridge(argv[1:])

    paths = get_paths()
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or default_command(paths)

    try:
        if command == "init":
            return run_init(paths)
        if command == "enable":
            return run_enable(paths)
        if command == "disable":
            return run_disable()
        if command == "status":
            print_status(paths)
            return 0
        if command == "stop":
            return run_stop(paths)
        if command == "reload":
            return run_reload(paths, background=False if args.debug else None)
        if command == "config":
            show_config(paths)
            return 0
        if command == "config-path":
            console.print(str(paths.config_file))
            return 0
        if command in {"account", "a"}:
            account_command = args.account_command or "list"
            if account_command in {"list", "ls"}:
                return run_account_list(paths)
            if account_command == "add":
                return run_account_add(paths, args.name)
            if account_command == "edit":
                return run_account_edit(paths, args.name)
            if account_command == "delete":
                return run_account_delete(paths, args.name)
            if account_command in {"use", "switch"}:
                return run_account_switch(paths, args.name)
            parser.print_help()
            return 1
        if command == "bootstrap-ca":
            ensure_domain_cert(paths)
            console.print(str(paths.root_ca_cert))
            console.print(str(paths.domain_crt(get_target_host())))
            return 0
        if command == "install-ca":
            install_ca(paths)
            return 0
        if command == "install-nss":
            install_nss(paths)
            return 0
        if command == "install-hosts":
            install_hosts()
            return 0
        if command == "remove-hosts":
            remove_hosts()
            return 0
        if command == "start":
            return run_start(paths, background=not args.debug)
        if command == "log":
            return run_log(paths)
        if command == "version":
            console.print(app_version())
            return 0
        parser.print_help()
        return 1
    except CliError as exc:
        console.print(f"[bold red]{t('error_label')}[/bold red] {exc}")
        return 1
    except KeyboardInterrupt:
        safe_interrupt_notice(t("cancelled"))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
