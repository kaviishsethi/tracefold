from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(10)}"


def sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(s: str | None, default=None):
    return json.loads(s) if s else default
