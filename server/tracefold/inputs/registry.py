"""Bounded in-memory registry of immutable private captures.

Raw private bytes live only here (never on disk in the default ephemeral mode). A restart invalidates
all captures; scans that reference an expired capture fail with ``input_expired``.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..config import Limits
from ..errors import ApiError
from ..util import now


@dataclass
class CapturedFile:
    file_id: str
    path: str                 # workspace-relative path, or sanitized upload display name
    status: str               # captured | deleted | rejected
    data: bytes | None = None
    sha256: str | None = None
    size: int | None = None
    kind: str | None = None   # text | code | docx
    language: str | None = None
    reason: str | None = None
    change: str | None = None  # added | modified | deleted | renamed | untracked (Git captures)
    old_path: str | None = None


@dataclass
class Capture:
    input_id: str
    workspace_id: str
    revision: int
    source: str
    files: list[CapturedFile]
    manifest_digest: str
    created_at: datetime
    expires_at: datetime
    baseline: str | None = None
    omitted_context: list[str] = field(default_factory=list)
    pins: int = 0
    consumed: bool = False

    @property
    def raw_bytes(self) -> int:
        return sum(len(f.data or b"") for f in self.files)

    def file(self, file_id: str) -> CapturedFile | None:
        return next((f for f in self.files if f.file_id == file_id), None)


class CaptureRegistry:
    def __init__(self, limits: Limits):
        self.limits = limits
        self._lock = threading.Lock()
        self._caps: dict[str, Capture] = {}

    def _expire_locked(self, t: datetime) -> None:
        for k in [k for k, c in self._caps.items() if c.pins == 0 and c.expires_at <= t]:
            del self._caps[k]

    def add(self, cap: Capture) -> None:
        with self._lock:
            t = now()
            self._expire_locked(t)
            need = cap.raw_bytes
            while len(self._caps) >= self.limits.max_captures or (
                sum(c.raw_bytes for c in self._caps.values()) + need > self.limits.max_captured_raw_bytes
            ):
                # Evict the oldest capture that is unpinned and already consumed by a finished scan.
                victims = sorted((c for c in self._caps.values() if c.pins == 0 and c.consumed), key=lambda c: c.created_at)
                if not victims:
                    raise ApiError(429, "capture_capacity", "Private capture capacity is full; wait for active scans to finish.", True)
                del self._caps[victims[0].input_id]
            self._caps[cap.input_id] = cap

    def get(self, input_id: str) -> Capture | None:
        with self._lock:
            self._expire_locked(now())
            return self._caps.get(input_id)

    def pin(self, input_id: str) -> Capture | None:
        with self._lock:
            self._expire_locked(now())
            c = self._caps.get(input_id)
            if c:
                c.pins += 1
            return c

    def unpin(self, input_id: str, consumed: bool = True) -> None:
        with self._lock:
            c = self._caps.get(input_id)
            if c:
                c.pins = max(0, c.pins - 1)
                if consumed:
                    c.consumed = True
                    c.expires_at = max(c.expires_at, now() + timedelta(seconds=self.limits.capture_ttl_seconds))

    def drop(self, input_id: str) -> None:
        with self._lock:
            self._caps.pop(input_id, None)

    def clear(self) -> None:
        with self._lock:
            self._caps.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._caps)
