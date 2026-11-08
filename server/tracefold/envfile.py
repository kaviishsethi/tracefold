"""Minimal .env loader for local provider keys. Existing environment variables always win; values are never logged."""
from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path | str | None = None) -> list[str]:
    p = Path(path) if path else Path(os.environ.get("TRACEFOLD_ENV_FILE", Path.cwd() / ".env"))
    if not p.is_file():
        return []
    loaded = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.removeprefix("export ").split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
            loaded.append(k)
    return loaded
