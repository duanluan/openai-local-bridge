import json
import os
from urllib.parse import urlparse

from mitmproxy import ctx
from mitmproxy import http


TARGET_HOST = os.environ.get("TARGET_HOST", "api.openai.com")
UPSTREAM_BASE = os.environ["UPSTREAM_BASE"].rstrip("/")
UPSTREAM_KEY = os.environ["UPSTREAM_KEY"]
UPSTREAM_MODEL = os.environ.get("UPSTREAM_MODEL", "").strip()

model_map_raw = os.environ.get("MODEL_MAP_JSON", "").strip()
MODEL_MAP = {}
if model_map_raw:
    parsed = json.loads(model_map_raw)
    if not isinstance(parsed, dict):
        raise ValueError("MODEL_MAP_JSON must be a JSON object")
    MODEL_MAP = {str(k): str(v) for k, v in parsed.items()}

parsed_upstream = urlparse(UPSTREAM_BASE)
if not parsed_upstream.scheme or not parsed_upstream.netloc:
    raise ValueError("UPSTREAM_BASE must be a full URL")


def _rewrite_model(data: dict) -> None:
    current = data.get("model")
    if not isinstance(current, str):
        return

    if UPSTREAM_MODEL:
        data["model"] = UPSTREAM_MODEL
        return

    mapped = MODEL_MAP.get(current)
    if mapped:
        data["model"] = mapped


def request(flow: http.HTTPFlow) -> None:
    if flow.request.pretty_host != TARGET_HOST:
        return

    suffix = flow.request.path
    if suffix == "/v1":
        suffix = ""
    elif suffix.startswith("/v1/"):
        suffix = suffix[3:]

    flow.request.url = f"{UPSTREAM_BASE}{suffix}"
    flow.request.scheme = parsed_upstream.scheme
    flow.request.host = parsed_upstream.hostname or flow.request.host
    flow.request.port = parsed_upstream.port or (443 if parsed_upstream.scheme == "https" else 80)
    flow.request.headers["Host"] = parsed_upstream.netloc
    flow.request.headers["Authorization"] = f"Bearer {UPSTREAM_KEY}"
    flow.request.headers.pop("OpenAI-Organization", None)
    flow.request.headers.pop("OpenAI-Project", None)

    ctype = flow.request.headers.get("content-type", "")
    if not ctype.startswith("application/json"):
        return

    try:
        data = json.loads(flow.request.get_text(strict=False))
    except Exception:
        return

    if isinstance(data, dict):
        before = data.get("model")
        _rewrite_model(data)
        after = data.get("model")
        if before != after:
            ctx.log.info(f"rewrote model: {before} -> {after}")
        flow.request.set_text(json.dumps(data, ensure_ascii=False))
