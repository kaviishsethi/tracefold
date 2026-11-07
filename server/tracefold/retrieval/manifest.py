"""Operator-approved public source manifests. Clients reference source IDs, never raw URLs."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..errors import ApiError

PROVIDERS = {"fixture", "direct", "exa", "tavily"}
_SID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def validate_sources(sources: list[dict]) -> list[dict]:
    out, seen = [], set()
    for s in sources:
        sid, url, provider = s.get("source_id"), s.get("url"), s.get("provider", "direct")
        if not sid or not _SID.match(sid) or sid in seen:
            raise ApiError(422, "invalid_manifest", "Each source needs a unique source_id.")
        if provider not in PROVIDERS:
            raise ApiError(422, "invalid_manifest", f"Unknown provider for {sid}.")
        parts = urlsplit(url or "")
        if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
            raise ApiError(422, "invalid_manifest", f"Source {sid} needs an http(s) URL without credentials.")
        entry = {"source_id": sid, "url": url, "provider": provider, "mode": s.get("mode", "seeded")}
        if provider == "fixture":
            if not s.get("fixture_path"):
                raise ApiError(422, "invalid_manifest", f"Fixture source {sid} needs fixture_path.")
            entry["fixture_path"] = s["fixture_path"]
        seen.add(sid)
        out.append(entry)
    return out
