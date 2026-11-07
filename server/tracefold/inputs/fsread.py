"""Safe reads inside a registered workspace root.

Validation happens at open time: every path component is lstat'ed and symlinks are refused, the final
component is opened with O_NOFOLLOW, and the opened descriptor must be a regular file whose identity
matches the lstat result. Special files, traversal and excluded paths are rejected.
"""
from __future__ import annotations

import fnmatch
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ALWAYS_EXCLUDED = [".git", ".git/*", "*/.git/*", ".env", "*/.env", ".env.*", "*/.env.*"]


class UnsafePath(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class ReadResult:
    data: bytes
    size: int
    mtime_ns: int
    ino: int
    dev: int


def normalize_rel(rel: str) -> str:
    if not rel or "\x00" in rel or "\\" in rel or len(rel) > 1024:
        raise UnsafePath("invalid_path")
    p = PurePosixPath(rel)
    if p.is_absolute() or any(part in ("..", "") for part in p.parts):
        raise UnsafePath("path_traversal")
    norm = p.as_posix()
    if norm.startswith("./"):
        norm = norm[2:]
    if norm in (".",):
        raise UnsafePath("invalid_path")
    return norm


def is_excluded(rel: str, excludes: list[str]) -> bool:
    if rel.endswith(".env.example"):
        return any(fnmatch.fnmatch(rel, pat) for pat in excludes)
    return any(fnmatch.fnmatch(rel, pat) for pat in [*ALWAYS_EXCLUDED, *excludes])


def read_file(root: Path, rel: str, max_bytes: int, excludes: list[str] | None = None) -> ReadResult:
    rel = normalize_rel(rel)
    if is_excluded(rel, excludes or []):
        raise UnsafePath("excluded_path")
    root_real = Path(os.path.realpath(root))
    cur = root_real
    parts = PurePosixPath(rel).parts
    st = None
    for i, part in enumerate(parts):
        cur = cur / part
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            raise UnsafePath("not_found")
        if stat.S_ISLNK(st.st_mode):
            raise UnsafePath("symlink_refused")
        if i < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
            raise UnsafePath("not_found")
    assert st is not None
    if not stat.S_ISREG(st.st_mode):
        raise UnsafePath("special_file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(cur, flags)
    except OSError:
        raise UnsafePath("open_failed")
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or (fst.st_ino, fst.st_dev) != (st.st_ino, st.st_dev):
            raise UnsafePath("changed_during_open")
        if fst.st_size > max_bytes:
            raise UnsafePath("too_large")
        chunks, total = [], 0
        while True:
            b = os.read(fd, min(1 << 20, max_bytes + 1 - total))
            if not b:
                break
            chunks.append(b)
            total += len(b)
            if total > max_bytes:
                raise UnsafePath("too_large")
        return ReadResult(b"".join(chunks), total, fst.st_mtime_ns, fst.st_ino, fst.st_dev)
    finally:
        os.close(fd)


def restat(root: Path, rel: str) -> tuple[int, int, int, int] | None:
    try:
        st = os.lstat(Path(os.path.realpath(root)) / normalize_rel(rel))
    except (FileNotFoundError, UnsafePath):
        return None
    return st.st_size, st.st_mtime_ns, st.st_ino, st.st_dev
