#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table


APP_SLUG = "openai-local-bridge"
APP_TITLE = "OpenAI Local Bridge"
DEFAULT_TARGET_HOST = "api.openai.com"
DEFAULT_HOSTS_IP = "127.0.0.1"
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = "443"
DEFAULT_REASONING_EFFORT = "medium"
DEFAULT_REASONING_FORMAT = "openai"
HOSTS_BEGIN = f"# BEGIN {APP_SLUG}"
HOSTS_END = f"# END {APP_SLUG}"
ROOT_CA_NAME = f"{APP_SLUG}-root-ca"
BAD_MODEL_VALUES = {"your-model-id", "你的上游模型ID", "your_model_id"}
REASONING_EFFORT_CHOICES = ["minimal", "low", "medium", "high", "xhigh"]

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
        return "0.1.0"


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
        raise CliError("missing command: openssl; Windows 请先安装 OpenSSL，并确认 openssl 已加入 PATH，再重新执行 olb enable / olb start")
    raise CliError(f"missing command: {name}")


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
        raise CliError(f"command failed: {' '.join(command)}") from exc
    except FileNotFoundError as exc:
        try:
            require_command(command[0])
        except CliError as missing:
            raise missing from exc
        raise CliError(f"missing command: {command[0]}") from exc


def run_privileged(command: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    if detect_os() == "windows":
        return run_command(command, capture_output=capture_output)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return run_command(command, capture_output=capture_output)
    require_command("sudo")
    return run_command(["sudo", *command], capture_output=capture_output)


def load_config(paths: AppPaths) -> dict[str, Any]:
    if not paths.config_file.exists():
        return {}
    return json.loads(paths.config_file.read_text(encoding="utf-8"))


def save_config(paths: AppPaths, config: dict[str, Any]) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        "推理强度",
        choices=reasoning_effort_choices(default_effort),
        default=default_effort,
    ).strip()


def should_elevate_for_listener(listen_port: str | int) -> bool:
    if detect_os() == "windows":
        return False
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return False
    return 0 < int(str(listen_port).strip()) < 1024


def preserved_olb_env_names(env: dict[str, str]) -> str:
    return ",".join(sorted(name for name in env if name.startswith("OLB_")))


def build_proxy_command(domain_crt: Path, domain_key: Path, env: dict[str, str]) -> list[str]:
    command = [sys.executable, "-m", "openai_local_bridge", "--cert", str(domain_crt), "--key", str(domain_key)]
    if not should_elevate_for_listener(env.get("OLB_LISTEN_PORT", DEFAULT_LISTEN_PORT)):
        return command

    require_command("sudo")
    preserved = preserved_olb_env_names(env)
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
        raise CliError("OLB_UPSTREAM_BASE is required")

    parsed = urlparse(upstream)
    if not parsed.scheme or not parsed.netloc:
        raise CliError("invalid OLB_UPSTREAM_BASE")
    if parsed.hostname == target:
        raise CliError("OLB_UPSTREAM_BASE host must not equal OLB_TARGET_HOST")

    upstream_model = str(config.get("upstream_model", "")).strip()
    if upstream_model in BAD_MODEL_VALUES:
        raise CliError("replace OLB_UPSTREAM_MODEL with the real upstream model id")

    model_map_raw = json.dumps(config.get("model_map", {}), ensure_ascii=False).lower()
    if "your-model-id" in model_map_raw or "你的上游模型id" in model_map_raw:
        raise CliError("replace OLB_MODEL_MAP_JSON placeholder with the real upstream model id")


def prompt_for_config(existing: dict[str, Any]) -> dict[str, Any]:
    console.print(Panel.fit("首次启动会写入你的上游配置，之后可随时重新执行 olb init 修改。示例值仅用于演示格式；如果提示里出现你自己的地址或参数，那就是当前已保存值。", title=APP_TITLE))

    old_base = str(existing.get("upstream_base", "")).strip()
    if old_base:
        base_prompt = "Base URL（回车保留当前已保存值）"
        default_base = old_base
    else:
        base_prompt = "Base URL（默认示例值仅作格式参考）"
        default_base = "https://your-openai-compatible.example/v1"
    base_url = Prompt.ask(base_prompt, default=default_base).strip()

    old_key = str(existing.get("upstream_key", ""))
    if old_key:
        entered_key = Prompt.ask(f"API Key（留空保留当前已保存值 {mask_secret(old_key)}）", password=True, default="").strip()
        api_key = entered_key or old_key
    else:
        api_key = Prompt.ask("API Key", password=True).strip()

    old_effort = str(existing.get("reasoning_effort", "")).strip()
    default_effort = old_effort or DEFAULT_REASONING_EFFORT
    if old_effort:
        reasoning_prompt = "推理强度（回车保留当前已保存值）"
    else:
        reasoning_prompt = "推理强度（默认值）"
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
        raise CliError("OLB_UPSTREAM_KEY is required")
    return config


def ensure_config(paths: AppPaths, *, interactive: bool) -> dict[str, Any]:
    config = load_config(paths)
    required = ["upstream_base", "upstream_key", "reasoning_effort"]
    if all(str(config.get(key, "")).strip() for key in required):
        validate_upstream(config)
        return config
    if not interactive:
        raise CliError(f"missing config: {paths.config_file}")
    config = prompt_for_config(config)
    save_config(paths, config)
    console.print(f"配置已保存到 [bold]{paths.config_file}[/bold]")
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
        console.print("根证书已导入 CurrentUser\\Root")
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
        console.print("根证书已导入系统钥匙串")
        return

    if strategy == "trust":
        run_privileged(["trust", "anchor", str(paths.root_ca_cert)])
        if shutil.which("update-ca-certificates"):
            run_privileged(["update-ca-certificates"])
        elif shutil.which("update-ca-trust"):
            run_privileged(["update-ca-trust", "extract"])
        else:
            run_privileged(["trust", "extract-compat"])
        console.print("根证书已通过 trust 导入")
        return

    if strategy == "update-ca-certificates":
        anchor_dir = Path("/usr/local/share/ca-certificates")
        anchor_file = anchor_dir / f"{ROOT_CA_NAME}.crt"
        run_privileged(["install", "-d", "-m", "0755", str(anchor_dir)])
        run_privileged(["install", "-m", "0644", str(paths.root_ca_cert), str(anchor_file)])
        run_privileged(["update-ca-certificates"])
        console.print(f"根证书已写入 {anchor_file}")
        return

    if strategy == "update-ca-trust":
        anchor_dir = Path("/etc/pki/ca-trust/source/anchors")
        anchor_file = anchor_dir / f"{ROOT_CA_NAME}.crt"
        run_privileged(["install", "-d", "-m", "0755", str(anchor_dir)])
        run_privileged(["install", "-m", "0644", str(paths.root_ca_cert), str(anchor_file)])
        run_privileged(["update-ca-trust", "extract"])
        console.print(f"根证书已写入 {anchor_file}")
        return

    raise CliError("unable to install CA automatically on this distribution")


def install_nss(paths: AppPaths) -> None:
    system = detect_os()
    if system in {"windows", "macos"}:
        console.print("当前平台无需额外导入 NSS")
        return

    require_command("certutil")
    ensure_root_ca(paths)
    nss_db = f"sql:{paths.nss_db_dir}"
    paths.nss_db_dir.mkdir(parents=True, exist_ok=True)

    if not (paths.nss_db_dir / "cert9.db").exists():
        run_command(["certutil", "-d", nss_db, "-N", "--empty-password"])

    run_command(["certutil", "-d", nss_db, "-D", "-n", APP_SLUG], check=False, capture_output=True)
    run_command(["certutil", "-d", nss_db, "-A", "-t", "C,,", "-n", APP_SLUG, "-i", str(paths.root_ca_cert)])
    console.print(f"根证书已导入 {nss_db}")


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
    console.print(f"hosts 已写入 {hosts_file}")


def remove_hosts() -> None:
    hosts_file = get_hosts_file()
    existing = hosts_file.read_text(encoding="utf-8") if hosts_file.exists() else ""
    cleaned = strip_hosts_entries(existing)
    write_hosts(cleaned)
    console.print(f"hosts 已从 {hosts_file} 清理")


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
        "config": str(paths.config_file),
    }


def print_status(paths: AppPaths) -> None:
    data = status_data(paths)
    table = Table(title="OpenAI Local Bridge 状态")
    table.add_column("项")
    table.add_column("值")
    for key, value in data.items():
        table.add_row(key, value)
    console.print(table)


def show_config(paths: AppPaths) -> None:
    config = load_config(paths)
    if not config:
        console.print(f"尚未创建配置文件：{paths.config_file}")
        return
    table = Table(title="当前配置")
    table.add_column("项")
    table.add_column("值")
    for key in ["upstream_base", "reasoning_effort", "reasoning_effort_format", "upstream_model"]:
        table.add_row(key, str(config.get(key, "")))
    table.add_row("upstream_key", mask_secret(str(config.get("upstream_key", ""))))
    table.add_row("config_path", str(paths.config_file))
    console.print(table)


def start_proxy(paths: AppPaths, config: dict[str, Any]) -> int:
    validate_upstream(config)
    domain_crt, domain_key = ensure_domain_cert(paths)
    env = env_from_config(config)
    listen_host = env.get("OLB_LISTEN_HOST", DEFAULT_LISTEN_HOST)
    listen_port = env.get("OLB_LISTEN_PORT", DEFAULT_LISTEN_PORT)
    console.print(
        Panel.fit(
            f"target_host={get_target_host()}\nlisten={listen_host}:{listen_port}\nupstream={config['upstream_base']}",
            title="启动桥接器",
        )
    )
    result = subprocess.run(build_proxy_command(domain_crt, domain_key, env), env=env)
    return result.returncode


def run_init(paths: AppPaths) -> int:
    config = prompt_for_config(load_config(paths))
    save_config(paths, config)
    console.print(f"配置已保存到 [bold]{paths.config_file}[/bold]")
    if Confirm.ask("现在展示当前配置吗？", default=True):
        show_config(paths)
    return 0


def run_enable(paths: AppPaths) -> int:
    install_ca(paths)
    install_nss(paths)
    install_hosts()
    return 0


def run_disable() -> int:
    remove_hosts()
    return 0


def run_start(paths: AppPaths) -> int:
    if not paths.config_file.exists():
        console.print("未检测到配置，先进入初始化。初始化完成后会继续执行 enable 和 start。")
    config = ensure_config(paths, interactive=True)
    run_enable(paths)
    return start_proxy(paths, config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="olb")
    subparsers = parser.add_subparsers(dest="command")

    for name in ["init", "enable", "disable", "status", "start", "config", "config-path", "bootstrap-ca", "install-ca", "install-nss", "install-hosts", "remove-hosts", "version"]:
        subparsers.add_parser(name)

    return parser


def default_command(paths: AppPaths) -> str:
    return "status" if paths.config_file.exists() else "init"


def main() -> int:
    paths = get_paths()
    parser = build_parser()
    args = parser.parse_args()
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
        if command == "config":
            show_config(paths)
            return 0
        if command == "config-path":
            console.print(str(paths.config_file))
            return 0
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
            return run_start(paths)
        if command == "version":
            console.print(app_version())
            return 0
        parser.print_help()
        return 1
    except CliError as exc:
        console.print(f"[bold red]error:[/bold red] {exc}")
        return 1
    except KeyboardInterrupt:
        console.print("已取消")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
