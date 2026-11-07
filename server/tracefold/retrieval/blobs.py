"""Content-addressed public text blobs (public content only; one blob per hash)."""
from __future__ import annotations

import os
from pathlib import Path

from ..util import sha256


class BlobStore:
    def __init__(self, root: Path, max_bytes: int):
        self.root = root
        self.max_bytes = max_bytes

    def _path(self, h: str) -> Path:
        if not all(c in "0123456789abcdef" for c in h) or len(h) != 64:
            raise ValueError("bad hash")
        return self.root / h[:2] / f"{h}.txt"

    def put(self, text: str) -> str:
        h = sha256(text)
        p = self._path(h)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, p)
        return h

    def read(self, h: str) -> str | None:
        try:
            return self._path(h).read_text(encoding="utf-8")
        except (FileNotFoundError, ValueError):
            return None

    def total_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.root.rglob("*.txt"))

    def gc(self, keep: set[str]) -> int:
        """Remove unreferenced blobs (disposable cache) until under the size cap."""
        removed = 0
        files = sorted(self.root.rglob("*.txt"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        for p in files:
            if total <= self.max_bytes:
                break
            if p.stem not in keep:
                total -= p.stat().st_size
                p.unlink()
                removed += 1
        return removed
