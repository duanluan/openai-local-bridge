#!/usr/bin/env python3
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import ssl
import sys
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from olb_i18n import SUPPORTED_LANGUAGES, apply_language_override, install_argparse_i18n, t
import requests


LOG = logging.getLogger("openai_local_bridge")
SESSION = requests.Session()
SESSION.trust_env = False

HOP_BY_HOP_HEADERS = {
    "connection",
    "proxy-connection",
    "keep-alive",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def env_json(name: str, default: Any) -> Any:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return json.loads(raw)


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def background_log_path() -> Path | None:
    raw = os.environ.get("OLB_LOG_PATH", "").strip()
    return Path(raw) if raw else None


def configure_logging() -> None:
    config_kwargs = {
        "level": logging.DEBUG if SETTINGS["debug"] else logging.INFO,
        "format": "[%(asctime)s] %(levelname)s %(message)s",
        "force": True,
    }
    log_path = background_log_path()
    if log_path is None:
        logging.basicConfig(**config_kwargs)
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=env_int("OLB_LOG_MAX_BYTES", 1024 * 1024),
        backupCount=env_int("OLB_LOG_BACKUP_COUNT", 3),
        encoding="utf-8",
    )
    logging.basicConfig(handlers=[handler], **config_kwargs)


def build_upstream_url(base_url: str, raw_path: str) -> str:
    base = urlsplit(base_url.rstrip("/"))
    incoming = urlsplit(raw_path)

    if incoming.path == "/v1":
        suffix = ""
    elif incoming.path.startswith("/v1/"):
        suffix = incoming.path[3:]
    else:
        suffix = incoming.path

    upstream_path = f"{base.path.rstrip('/')}{suffix}"
    if not upstream_path:
        upstream_path = "/"

    return urlunsplit(
        SplitResult(
            scheme=base.scheme,
            netloc=base.netloc,
            path=upstream_path,
            query=incoming.query,
            fragment="",
        )
    )


def rewrite_model(payload: dict[str, Any], settings: dict[str, Any]) -> tuple[str | None, str | None]:
    requested_model = payload.get("model")
    if not isinstance(requested_model, str):
        return None, None

    upstream_model = settings["upstream_model"] or settings["model_map"].get(requested_model) or requested_model
    payload["model"] = upstream_model

    if settings["force_stream_mode"] is not None:
        payload["stream"] = settings["force_stream_mode"]

    return requested_model, upstream_model


def apply_reasoning_effort(payload: dict[str, Any], settings: dict[str, Any]) -> None:
    effort = settings["reasoning_effort"]
    if not effort:
        return

    fmt = settings["reasoning_effort_format"]

    if fmt in {"openai", "both"}:
        reasoning = payload.get("reasoning")
        if not isinstance(reasoning, dict):
            reasoning = {}
        reasoning["effort"] = effort
        payload["reasoning"] = reasoning

    if fmt in {"flat", "both"}:
        payload["reasoning_effort"] = effort


def exposed_models(settings: dict[str, Any]) -> list[str]:
    if settings["exposed_models"]:
        return settings["exposed_models"]
    if settings["model_map"]:
        return list(settings["model_map"].keys())
    return []


def build_settings() -> dict[str, Any]:
    upstream_base = os.environ["OLB_UPSTREAM_BASE"].rstrip("/")
    model_map = env_json("OLB_MODEL_MAP_JSON", {})
    exposed = env_json("OLB_EXPOSED_MODELS_JSON", [])
    force_stream_raw = os.environ.get("OLB_FORCE_STREAM_MODE", "").strip().lower()
    reasoning_effort_format = os.environ.get("OLB_REASONING_EFFORT_FORMAT", "openai").strip().lower() or "openai"

    if not isinstance(model_map, dict):
        raise ValueError(t("model_map_must_be_object"))
    if not isinstance(exposed, list):
        raise ValueError(t("exposed_models_must_be_array"))
    if reasoning_effort_format not in {"openai", "flat", "both"}:
        raise ValueError(t("reasoning_format_invalid"))

    force_stream = None
    if force_stream_raw:
        force_stream = force_stream_raw in {"1", "true", "yes", "on"}

    return {
        "target_host": os.environ.get("OLB_TARGET_HOST", "api.openai.com"),
        "listen_host": os.environ.get("OLB_LISTEN_HOST", "127.0.0.1"),
        "listen_port": int(os.environ.get("OLB_LISTEN_PORT", "443")),
        "upstream_base": upstream_base,
        "upstream_key": os.environ["OLB_UPSTREAM_KEY"],
        "upstream_model": os.environ.get("OLB_UPSTREAM_MODEL", "").strip(),
        "upstream_insecure": env_bool("OLB_UPSTREAM_INSECURE", False),
        "debug": env_bool("OLB_DEBUG", True),
        "model_map": {str(k): str(v) for k, v in model_map.items()},
        "exposed_models": [str(item) for item in exposed],
        "force_stream_mode": force_stream,
        "reasoning_effort": os.environ.get("OLB_REASONING_EFFORT", "").strip(),
        "reasoning_effort_format": reasoning_effort_format,
    }


SETTINGS = build_settings()


class StartupError(RuntimeError):
    pass


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "OpenAI"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.debug("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        self.handle_request()

    def do_POST(self) -> None:
        self.handle_request()

    def do_PUT(self) -> None:
        self.handle_request()

    def do_PATCH(self) -> None:
        self.handle_request()

    def do_DELETE(self) -> None:
        self.handle_request()

    def do_OPTIONS(self) -> None:
        self.handle_request()

    def do_HEAD(self) -> None:
        self.handle_request()

    def handle_request(self) -> None:
        parsed = urlsplit(self.path)

        if self.command == "GET" and parsed.path == "/healthz":
            self.send_json(200, {"ok": True, "target_host": SETTINGS["target_host"]})
            return

        if self.command == "GET" and parsed.path in {"/", "/favicon.ico"}:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if self.command == "GET" and parsed.path == "/v1/models":
            models = exposed_models(SETTINGS)
            if models:
                self.send_json(
                    200,
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": model,
                                "object": "model",
                                "created": 0,
                                "owned_by": "openai-local-bridge",
                            }
                            for model in models
                        ],
                    },
                )
                return

        body = self.read_body()
        outgoing_headers = self.prepare_headers()
        upstream_url = build_upstream_url(SETTINGS["upstream_base"], self.path)
        requested_model = None
        upstream_model = None

        content_type = self.headers.get("Content-Type", "")
        if body and content_type.lower().startswith("application/json"):
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                requested_model, upstream_model = rewrite_model(payload, SETTINGS)
                apply_reasoning_effort(payload, SETTINGS)
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if requested_model and upstream_model and requested_model != upstream_model:
                    LOG.info("rewrite model %s -> %s", requested_model, upstream_model)
                if SETTINGS["reasoning_effort"]:
                    LOG.info(
                        "set reasoning effort=%s format=%s",
                        SETTINGS["reasoning_effort"],
                        SETTINGS["reasoning_effort_format"],
                    )

        if body:
            outgoing_headers["Content-Length"] = str(len(body))

        outgoing_headers["Authorization"] = f"Bearer {SETTINGS['upstream_key']}"
        outgoing_headers.pop("OpenAI-Organization", None)
        outgoing_headers.pop("OpenAI-Project", None)
        outgoing_headers["Accept-Encoding"] = "identity"

        LOG.info("%s %s -> %s", self.command, parsed.path or "/", upstream_url)

        try:
            response = SESSION.request(
                method=self.command,
                url=upstream_url,
                headers=outgoing_headers,
                data=body if body else None,
                stream=True,
                timeout=(30, 1800),
                verify=not SETTINGS["upstream_insecure"],
            )
        except requests.RequestException as exc:
            LOG.error("upstream request failed: %s", exc)
            self.send_json(502, {"error": str(exc)})
            return

        if response.status_code >= 400:
            snippet = response.text[:2000]
            LOG.error("upstream error status=%s body=%s", response.status_code, snippet)

        with response:
            self.relay_response(response, requested_model, upstream_model)

    def prepare_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        for name, value in self.headers.items():
            if name.lower() in HOP_BY_HOP_HEADERS:
                continue
            headers[name] = value
        return headers

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def relay_response(
        self,
        response: requests.Response,
        requested_model: str | None,
        upstream_model: str | None,
    ) -> None:
        content_type = response.headers.get("Content-Type", "")
        is_event_stream = "text/event-stream" in content_type.lower()

        if is_event_stream:
            self.send_response(response.status_code)
            self.copy_response_headers(response, streaming=True)
            self.end_headers()

            if self.command == "HEAD":
                return

            rewrite_from = None
            rewrite_to = None
            if requested_model and upstream_model and requested_model != upstream_model:
                rewrite_from = upstream_model.encode("utf-8")
                rewrite_to = requested_model.encode("utf-8")

            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    if rewrite_from and rewrite_to:
                        chunk = chunk.replace(rewrite_from, rewrite_to)
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except BrokenPipeError:
                LOG.info("client disconnected during stream")
            return

        response_body = response.content

        if "application/json" in content_type.lower():
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict) and requested_model and "model" in payload:
                payload["model"] = requested_model
                response_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(response.status_code)
        self.copy_response_headers(response, streaming=False, body_len=len(response_body))
        self.end_headers()

        if self.command != "HEAD":
            self.wfile.write(response_body)

    def copy_response_headers(
        self,
        response: requests.Response,
        streaming: bool,
        body_len: int | None = None,
    ) -> None:
        for name, value in response.headers.items():
            lower = name.lower()
            if lower in HOP_BY_HOP_HEADERS:
                continue
            if streaming and lower == "content-length":
                continue
            self.send_header(name, value)

        if not streaming and body_len is not None:
            self.send_header("Content-Length", str(body_len))

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list([] if argv is None else argv)
    apply_language_override(argv)
    install_argparse_i18n()
    parser = argparse.ArgumentParser(description=t("bridge_description"))
    parser.add_argument("--lang", choices=list(SUPPORTED_LANGUAGES), help=t("language_arg_help"))
    parser.add_argument("--cert", required=True, help=t("bridge_cert_help"))
    parser.add_argument("--key", required=True, help=t("bridge_key_help"))
    parser.add_argument("--pid-file", help=t("bridge_pid_file_help"))
    return parser.parse_args(argv)


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


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def pid_file_guard(pid_file: str | None):
    if not pid_file:
        yield None
        return

    path = Path(pid_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_pid = read_pid_file(path)
    if existing_pid is not None and existing_pid != os.getpid() and process_exists(existing_pid):
        raise StartupError(t("bridge_already_running", pid=existing_pid))

    path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    try:
        yield path
    finally:
        current_pid = read_pid_file(path)
        if current_pid is None or current_pid == os.getpid():
            path.unlink(missing_ok=True)


def install_signal_handlers() -> dict[int, Any]:
    previous: dict[int, Any] = {}

    def handle_shutdown(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame, None)
        if sig is None:
            continue
        previous[sig] = signal.getsignal(sig)
        signal.signal(sig, handle_shutdown)
    return previous


def restore_signal_handlers(previous: dict[int, Any]) -> None:
    for sig, handler in previous.items():
        signal.signal(sig, handler)


def create_server() -> ThreadingHTTPServer:
    host = SETTINGS["listen_host"]
    port = SETTINGS["listen_port"]

    try:
        return ThreadingHTTPServer((host, port), ProxyHandler)
    except PermissionError as exc:
        raise StartupError(t("bridge_bind_error", host=host, port=port)) from exc


def main(argv: list[str] | None = None) -> int:
    apply_language_override(list(sys.argv[1:] if argv is None else argv))
    args = parse_args(argv)
    configure_logging()

    server = create_server()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=args.cert, keyfile=args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    previous_handlers = install_signal_handlers()

    LOG.info(
        "listen https://%s:%s -> %s",
        SETTINGS["listen_host"],
        SETTINGS["listen_port"],
        SETTINGS["upstream_base"],
    )

    try:
        with pid_file_guard(args.pid_file):
            server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("bridge stopped")
    finally:
        restore_signal_handlers(previous_handlers)
        server.server_close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StartupError as exc:
        if background_log_path() is not None:
            LOG.error("%s", exc)
        else:
            print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
