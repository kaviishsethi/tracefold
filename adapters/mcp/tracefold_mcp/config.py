"""Local adapter configuration.

The engine URL, client token and default workspace come only from a local, owner-only config file that an
operator writes (``tracefold-mcp configure``). Nothing here can be set by the MCP host through tool
arguments: the host cannot point the adapter at another server, swap the token or choose a filesystem root.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ENV_CONFIG = "TRACEFOLD_MCP_CONFIG"
DEFAULT_CONFIG = Path.home() / ".config" / "tracefold" / "mcp.json"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ConfigError(Exception):
    """The adapter configuration is missing or unsafe. Messages never include the token."""


@dataclass(frozen=True)
class AdapterConfig:
    base_url: str  # e.g. http://127.0.0.1:8787 (no /v1)
    token: str
    workspace_id: str
    timeout_seconds: float = 30.0

    def __repr__(self) -> str:  # never print the token
        return f"AdapterConfig(base_url={self.base_url!r}, workspace_id={self.workspace_id!r}, token='***')"


def validate_base_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS:
        raise ConfigError("base_url must be an http:// loopback address (127.0.0.1, localhost or ::1)")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ConfigError("base_url must not carry credentials, a query or a fragment")
    path = parts.path.rstrip("/")
    if path not in ("", "/v1"):
        raise ConfigError("base_url must be the engine origin, optionally ending in /v1")
    return f"{parts.scheme}://{parts.netloc}"


def config_path(explicit: str | os.PathLike | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get(ENV_CONFIG)
    return Path(env).expanduser() if env else DEFAULT_CONFIG


def load_config(path: str | os.PathLike | None = None) -> AdapterConfig:
    p = config_path(path)
    try:
        st = p.stat()
    except FileNotFoundError:
        raise ConfigError(f"no adapter config at {p}; run `tracefold-mcp configure` first") from None
    if os.name == "posix" and stat.S_IMODE(st.st_mode) & 0o077:
        raise ConfigError(f"{p} is readable by other users; run `chmod 600 {p}`")
    try:
        raw = json.loads(p.read_text())
    except (OSError, ValueError):
        raise ConfigError(f"{p} is not valid JSON") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{p} must contain a JSON object")
    token = raw.get("token")
    ws = raw.get("workspace_id")
    if not isinstance(token, str) or not token.startswith("tf_"):
        raise ConfigError("config 'token' must be a Tracefold client token (tf_…)")
    if not isinstance(ws, str) or not ws:
        raise ConfigError("config 'workspace_id' is required")
    timeout = raw.get("timeout_seconds", 30.0)
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 120:
        raise ConfigError("config 'timeout_seconds' must be between 1 and 120")
    return AdapterConfig(base_url=validate_base_url(str(raw.get("base_url", "http://127.0.0.1:8787"))),
                         token=token, workspace_id=ws, timeout_seconds=float(timeout))


def write_config(path: str | os.PathLike | None, base_url: str, token: str, workspace_id: str) -> Path:
    p = config_path(path)
    cfg = {"base_url": validate_base_url(base_url), "token": token.strip(), "workspace_id": workspace_id}
    if not cfg["token"].startswith("tf_"):
        raise ConfigError("token must be a Tracefold client token (tf_…)")
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    os.chmod(p, 0o600)
    return p
