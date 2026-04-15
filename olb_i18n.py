from __future__ import annotations

import argparse
import os


SUPPORTED_LANGUAGES = ("en", "zh")


MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "language_arg_help": "set command language",
        "cli_description": "Local OpenAI bridge CLI for OpenAI-compatible upstreams",
        "bridge_description": "Run the local HTTPS bridge process",
        "subcommands_title": "commands",
        "cmd_init_help": "interactively initialize upstream settings",
        "cmd_enable_help": "install certificates, NSS trust, and hosts mapping",
        "cmd_disable_help": "remove hosts mapping",
        "cmd_status_help": "show bridge status",
        "cmd_config_help": "show saved configuration",
        "cmd_config_path_help": "print the config file path",
        "cmd_account_help": "manage multiple upstream accounts",
        "cmd_account_list_help": "list saved accounts",
        "cmd_account_add_help": "add a new upstream account",
        "cmd_account_edit_help": "edit an existing upstream account",
        "cmd_account_delete_help": "delete an upstream account",
        "cmd_account_switch_help": "use the selected upstream account as active",
        "cmd_bootstrap_ca_help": "generate the local CA and target certificate",
        "cmd_install_ca_help": "install the root CA into the system trust store",
        "cmd_install_nss_help": "install the root CA into the NSS database",
        "cmd_install_hosts_help": "write the hosts mapping",
        "cmd_remove_hosts_help": "remove the hosts mapping",
        "cmd_version_help": "print the installed version",
        "cmd_stop_help": "stop the background bridge process",
        "cmd_start_help": "enable the environment and start the bridge",
        "start_background_help": "run bridge in background",
        "account_name_arg_help": "account name",
        "bridge_cert_help": "path to the TLS certificate file",
        "bridge_key_help": "path to the TLS private key file",
        "bridge_pid_file_help": "path to the PID file used for singleton checks",
        "config_intro_init": "Set the active account settings. You can rerun `olb init` any time to update them. Example values only show the format; if a prompt shows your own address or parameters, that value is already saved.",
        "config_intro_add": "Set the upstream settings for the new account. Example values only show the format. This account will not become active until you run `olb account use <name>`.",
        "config_intro_edit": "Update the selected account settings. Example values only show the format; if a prompt shows your own address or parameters, that value is already saved.",
        "base_prompt_saved": "Base URL (press Enter to keep the saved value)",
        "base_prompt_default": "Base URL (default example only shows the expected format)",
        "api_key_prompt": "API Key",
        "api_key_keep": "API Key (leave empty to keep the saved value {masked})",
        "reasoning_effort_label": "Reasoning effort",
        "reasoning_prompt_saved": "Reasoning effort (press Enter to keep the saved value)",
        "reasoning_prompt_default": "Reasoning effort (default value)",
        "config_saved": "Config saved to [bold]{path}[/bold]",
        "accounts_title": "Saved Accounts",
        "account_name_required": "account name is required",
        "account_exists": "account already exists: {name}",
        "account_not_found": "account not found: {name}",
        "accounts_empty": "no accounts configured yet",
        "account_added": "account added: {name}",
        "account_updated": "account updated: {name}",
        "account_deleted": "account deleted: {name}",
        "account_switched": "active account switched to {name}",
        "restart_bridge_after_account_switch": "bridge is running (PID {pid}). Restart it now in background to apply account {name}?",
        "root_ca_imported_windows": "Root CA imported into CurrentUser\\Root",
        "root_ca_imported_macos": "Root CA imported into the system keychain",
        "root_ca_imported_trust": "Root CA imported with trust",
        "root_ca_written": "Root CA written to {path}",
        "nss_not_needed": "This platform does not need an extra NSS import",
        "nss_imported": "Root CA imported into {path}",
        "hosts_written": "hosts written to {path}",
        "hosts_removed": "hosts entries removed from {path}",
        "status_title": "OpenAI Local Bridge Status",
        "config_title": "Current Config",
        "table_item": "Item",
        "table_value": "Value",
        "field_label_active_account": "Active Account",
        "field_label_accounts": "Saved Accounts",
        "field_label_upstream_base": "API Request URL",
        "field_label_reasoning_effort": "Reasoning Effort Level",
        "field_label_reasoning_effort_format": "Reasoning Effort Format",
        "field_label_upstream_model": "Upstream Model",
        "field_label_upstream_key": "API Key",
        "field_label_config_path": "Config Path",
        "config_missing": "Config file has not been created yet: {path}",
        "bridge_running_background": "bridge is running in background, PID={pid}, log={log_path}",
        "bridge_start_panel_title": "Start Bridge",
        "bridge_start_panel_body": "target_host={target_host}\nlisten={listen}\nupstream={upstream}\nmode={mode}",
        "mode_background": "background",
        "mode_foreground": "foreground",
        "bridge_start_failed_detail": "bridge failed to start: {detail}",
        "bridge_start_failed_exit": "bridge failed to start, exit code {code}",
        "bridge_start_timeout": "bridge start timed out, check the log: {log_path}",
        "bridge_not_running": "bridge is not running",
        "bridge_stopped": "bridge stopped (PID {pid})",
        "cannot_stop_bridge": "unable to stop bridge (PID {pid})",
        "show_config_after_init": "Show the current config now?",
        "missing_config_start_notice": "No config detected. Starting interactive initialization first, then running enable and start.",
        "error_label": "error:",
        "cancelled": "Cancelled",
        "missing_command": "missing command: {name}",
        "missing_command_openssl_windows": "missing command: openssl; on Windows install OpenSSL, add it to PATH, then rerun olb enable / olb start",
        "command_failed": "command failed: {command}",
        "upstream_base_required": "OLB_UPSTREAM_BASE is required",
        "invalid_upstream_base": "invalid OLB_UPSTREAM_BASE",
        "upstream_base_host_conflict": "OLB_UPSTREAM_BASE host must not equal OLB_TARGET_HOST",
        "replace_upstream_model_placeholder": "replace OLB_UPSTREAM_MODEL with the real upstream model id",
        "replace_model_map_placeholder": "replace the OLB_MODEL_MAP_JSON placeholder with the real upstream model id",
        "upstream_key_required": "OLB_UPSTREAM_KEY is required",
        "missing_config": "missing config: {path}",
        "auto_ca_unsupported": "unable to install the CA automatically on this distribution",
        "sudo_command_required": "command must start with sudo",
        "status_label_os": "OS",
        "status_label_target_host": "Target Host",
        "status_label_hosts": "Hosts Mapping",
        "status_label_hosts_file": "Hosts File",
        "status_label_root_ca": "Root CA",
        "status_label_ca_install_strategy": "CA Install Strategy",
        "status_label_nss": "NSS",
        "status_label_nss_db": "NSS Database",
        "status_label_listener": "Listener",
        "status_label_listen_addr": "Listen Address",
        "status_label_active_account": "Active Account",
        "status_label_config": "Config Path",
        "status_value_enabled": "enabled",
        "status_value_disabled": "disabled",
        "status_value_present": "present",
        "status_value_missing": "missing",
        "status_value_unknown": "unknown",
        "status_value_not_applicable": "not applicable",
        "status_value_not_configured": "not configured",
        "status_value_listening": "listening",
        "status_value_stopped": "stopped",
        "bridge_already_running": "bridge already running (pid {pid})",
        "bridge_bind_error": "cannot bind https listener on {host}:{port}; choose OLB_LISTEN_PORT>=1024 or run with elevated privileges",
        "model_map_must_be_object": "OLB_MODEL_MAP_JSON must be a JSON object",
        "exposed_models_must_be_array": "OLB_EXPOSED_MODELS_JSON must be a JSON array",
        "reasoning_format_invalid": "OLB_REASONING_EFFORT_FORMAT must be one of: openai, flat, both",
    },
    "zh": {
        "language_arg_help": "设置命令语言",
        "cli_description": "OpenAI 兼容上游的本地桥接 CLI",
        "bridge_description": "运行本地 HTTPS bridge 进程",
        "subcommands_title": "命令",
        "cmd_init_help": "交互式初始化上游配置",
        "cmd_enable_help": "安装证书、NSS 信任和 hosts 映射",
        "cmd_disable_help": "移除 hosts 映射",
        "cmd_status_help": "查看 bridge 状态",
        "cmd_config_help": "查看已保存配置",
        "cmd_config_path_help": "输出配置文件路径",
        "cmd_account_help": "管理多个上游账号",
        "cmd_account_list_help": "查看已保存账号",
        "cmd_account_add_help": "新增上游账号",
        "cmd_account_edit_help": "修改已有上游账号",
        "cmd_account_delete_help": "删除上游账号",
        "cmd_account_switch_help": "使用指定上游账号作为当前账号",
        "cmd_bootstrap_ca_help": "生成本地 CA 和目标域名证书",
        "cmd_install_ca_help": "把根证书安装到系统信任库",
        "cmd_install_nss_help": "把根证书安装到 NSS 数据库",
        "cmd_install_hosts_help": "写入 hosts 映射",
        "cmd_remove_hosts_help": "移除 hosts 映射",
        "cmd_version_help": "输出已安装版本",
        "cmd_stop_help": "停止后台 bridge 进程",
        "cmd_start_help": "启用环境并启动 bridge",
        "start_background_help": "以后台模式运行 bridge",
        "account_name_arg_help": "账号名",
        "bridge_cert_help": "TLS 证书文件路径",
        "bridge_key_help": "TLS 私钥文件路径",
        "bridge_pid_file_help": "用于单实例检查的 PID 文件路径",
        "config_intro_init": "首次启动会写入当前账号的上游配置，之后可随时重新执行 `olb init` 修改。示例值仅用于演示格式；如果提示里出现你自己的地址或参数，那就是当前已保存值。",
        "config_intro_add": "现在为新账号写入上游配置。示例值仅用于演示格式。新增后不会自动切换，需要再执行 `olb account use <name>` 才会成为当前账号。",
        "config_intro_edit": "现在修改选中账号的上游配置。示例值仅用于演示格式；如果提示里出现你自己的地址或参数，那就是当前已保存值。",
        "base_prompt_saved": "Base URL（回车保留当前已保存值）",
        "base_prompt_default": "Base URL（默认示例值仅作格式参考）",
        "api_key_prompt": "API Key",
        "api_key_keep": "API Key（留空保留当前已保存值 {masked}）",
        "reasoning_effort_label": "推理强度",
        "reasoning_prompt_saved": "推理强度（回车保留当前已保存值）",
        "reasoning_prompt_default": "推理强度（默认值）",
        "config_saved": "配置已保存到 [bold]{path}[/bold]",
        "accounts_title": "已保存账号",
        "account_name_required": "账号名不能为空",
        "account_exists": "账号已存在：{name}",
        "account_not_found": "账号不存在：{name}",
        "accounts_empty": "当前还没有已配置账号",
        "account_added": "已新增账号：{name}",
        "account_updated": "已更新账号：{name}",
        "account_deleted": "已删除账号：{name}",
        "account_switched": "当前账号已切换为：{name}",
        "restart_bridge_after_account_switch": "检测到 bridge 正在运行（PID {pid}）。是否现在以后台模式重启，让账号 {name} 立即生效？",
        "root_ca_imported_windows": "根证书已导入 CurrentUser\\Root",
        "root_ca_imported_macos": "根证书已导入系统钥匙串",
        "root_ca_imported_trust": "根证书已通过 trust 导入",
        "root_ca_written": "根证书已写入 {path}",
        "nss_not_needed": "当前平台无需额外导入 NSS",
        "nss_imported": "根证书已导入 {path}",
        "hosts_written": "hosts 已写入 {path}",
        "hosts_removed": "hosts 已从 {path} 清理",
        "status_title": "OpenAI Local Bridge 状态",
        "config_title": "当前配置",
        "table_item": "项",
        "table_value": "值",
        "field_label_active_account": "当前账号",
        "field_label_accounts": "已保存账号",
        "field_label_upstream_base": "API 请求地址",
        "field_label_reasoning_effort": "推理强度等级",
        "field_label_reasoning_effort_format": "推理强度格式",
        "field_label_upstream_model": "上游模型",
        "field_label_upstream_key": "API Key",
        "field_label_config_path": "配置路径",
        "config_missing": "尚未创建配置文件：{path}",
        "bridge_running_background": "bridge 已在后台运行，PID={pid}，日志={log_path}",
        "bridge_start_panel_title": "启动桥接器",
        "bridge_start_panel_body": "目标域名={target_host}\n监听={listen}\n上游={upstream}\n模式={mode}",
        "mode_background": "后台",
        "mode_foreground": "前台",
        "bridge_start_failed_detail": "bridge 启动失败：{detail}",
        "bridge_start_failed_exit": "bridge 启动失败，退出码 {code}",
        "bridge_start_timeout": "bridge 启动超时，请查看日志：{log_path}",
        "bridge_not_running": "bridge 未运行",
        "bridge_stopped": "bridge 已停止（PID {pid}）",
        "cannot_stop_bridge": "无法停止 bridge（PID {pid}）",
        "show_config_after_init": "现在展示当前配置吗？",
        "missing_config_start_notice": "未检测到配置，先进入初始化。初始化完成后会继续执行 enable 和 start。",
        "error_label": "错误：",
        "cancelled": "已取消",
        "missing_command": "缺少命令：{name}",
        "missing_command_openssl_windows": "缺少命令：openssl；Windows 请先安装 OpenSSL，并确认 openssl 已加入 PATH，再重新执行 olb enable / olb start",
        "command_failed": "命令执行失败：{command}",
        "upstream_base_required": "必须设置 OLB_UPSTREAM_BASE",
        "invalid_upstream_base": "OLB_UPSTREAM_BASE 不合法",
        "upstream_base_host_conflict": "OLB_UPSTREAM_BASE 的 host 不能与 OLB_TARGET_HOST 相同",
        "replace_upstream_model_placeholder": "请把 OLB_UPSTREAM_MODEL 替换成真实上游模型 ID",
        "replace_model_map_placeholder": "请把 OLB_MODEL_MAP_JSON 中的占位模型 ID 替换成真实值",
        "upstream_key_required": "必须设置 OLB_UPSTREAM_KEY",
        "missing_config": "缺少配置：{path}",
        "auto_ca_unsupported": "当前发行版暂不支持自动安装 CA",
        "sudo_command_required": "命令必须以 sudo 开头",
        "status_label_os": "系统",
        "status_label_target_host": "目标域名",
        "status_label_hosts": "Hosts 映射",
        "status_label_hosts_file": "Hosts 文件",
        "status_label_root_ca": "根证书",
        "status_label_ca_install_strategy": "CA 安装方式",
        "status_label_nss": "NSS",
        "status_label_nss_db": "NSS 数据库",
        "status_label_listener": "监听状态",
        "status_label_listen_addr": "监听地址",
        "status_label_active_account": "当前账号",
        "status_label_config": "配置路径",
        "status_value_enabled": "已启用",
        "status_value_disabled": "未启用",
        "status_value_present": "已存在",
        "status_value_missing": "缺失",
        "status_value_unknown": "未知",
        "status_value_not_applicable": "不适用",
        "status_value_not_configured": "未配置",
        "status_value_listening": "监听中",
        "status_value_stopped": "已停止",
        "bridge_already_running": "bridge 已在运行（PID {pid}）",
        "bridge_bind_error": "无法绑定 {host}:{port} 的 HTTPS 监听；请把 OLB_LISTEN_PORT 设为 >=1024，或使用提权方式运行",
        "model_map_must_be_object": "OLB_MODEL_MAP_JSON 必须是 JSON 对象",
        "exposed_models_must_be_array": "OLB_EXPOSED_MODELS_JSON 必须是 JSON 数组",
        "reasoning_format_invalid": "OLB_REASONING_EFFORT_FORMAT 只能是 openai、flat、both 之一",
    },
}


ARGPARSE_MESSAGES: dict[str, dict[str, str]] = {
    "usage: ": {"en": "usage: ", "zh": "用法："},
    "positional arguments": {"en": "positional arguments", "zh": "位置参数"},
    "options": {"en": "options", "zh": "选项"},
    "optional arguments": {"en": "optional arguments", "zh": "可选参数"},
    "show this help message and exit": {"en": "show this help message and exit", "zh": "显示帮助信息并退出"},
    "%(prog)s: error: %(message)s\n": {"en": "%(prog)s: error: %(message)s\n", "zh": "%(prog)s：错误：%(message)s\n"},
    "the following arguments are required: %s": {
        "en": "the following arguments are required: %s",
        "zh": "缺少以下必填参数：%s",
    },
    "one of the arguments %s is required": {
        "en": "one of the arguments %s is required",
        "zh": "以下参数中至少需要一个：%s",
    },
    "not allowed with argument %s": {"en": "not allowed with argument %s", "zh": "不能与参数 %s 同时使用"},
    "expected one argument": {"en": "expected one argument", "zh": "需要一个参数值"},
    "invalid choice: %(value)r (choose from %(choices)s)": {
        "en": "invalid choice: %(value)r (choose from %(choices)s)",
        "zh": "无效选项：%(value)r（可选值：%(choices)s）",
    },
    "unrecognized arguments: %s": {"en": "unrecognized arguments: %s", "zh": "无法识别的参数：%s"},
    "argument %(argument_name)s: %(message)s": {
        "en": "argument %(argument_name)s: %(message)s",
        "zh": "参数 %(argument_name)s：%(message)s",
    },
}


def normalize_language(raw: str | None) -> str:
    if not raw:
        return "en"
    normalized = raw.strip().split(".", 1)[0].split("@", 1)[0].lower().replace("-", "_")
    if normalized.startswith("zh"):
        return "zh"
    return "en"


def current_language() -> str:
    for name in ("OLB_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if value.strip():
            return normalize_language(value)
    return "en"


def apply_language_override(argv: list[str]) -> None:
    for index, arg in enumerate(argv):
        if arg == "--lang" and index + 1 < len(argv):
            os.environ["OLB_LANG"] = normalize_language(argv[index + 1])
            return
        if arg.startswith("--lang="):
            os.environ["OLB_LANG"] = normalize_language(arg.split("=", 1)[1])
            return


def t(key: str, **kwargs: object) -> str:
    lang = current_language()
    template = MESSAGES.get(lang, MESSAGES["en"]).get(key, MESSAGES["en"].get(key, key))
    return template.format(**kwargs)


def translate_status_label(key: str) -> str:
    return t(f"status_label_{key}")


def translate_status_value(value: str) -> str:
    lookup_key = f"status_value_{value}"
    lang = current_language()
    catalog = MESSAGES.get(lang, MESSAGES["en"])
    if lookup_key not in catalog and lookup_key not in MESSAGES["en"]:
        return value
    return t(lookup_key)


def translate_field_label(key: str) -> str:
    return t(f"field_label_{key}")


def _translate_argparse(message: str) -> str:
    lang = current_language()
    catalog = ARGPARSE_MESSAGES.get(message)
    if not catalog:
        return message
    return catalog.get(lang, catalog.get("en", message))


def _translate_argparse_ngettext(singular: str, plural: str, number: int) -> str:
    source = singular if number == 1 else plural
    return _translate_argparse(source)


def install_argparse_i18n() -> None:
    argparse._ = _translate_argparse
    argparse.ngettext = _translate_argparse_ngettext
