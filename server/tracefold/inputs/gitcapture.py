"""Capture saved working-tree changes against an explicit baseline commit.

Git is used only for plumbing reads that never touch working-tree content (``rev-parse``, ``ls-tree``,
``ls-files``), invoked as argument lists without a shell, with system/global config disabled and fsmonitor,
hooks and pagers neutralized. Working-tree bytes are read by Tracefold's safe reader and compared to baseline
blob IDs by hashing them ourselves, so repository-defined clean/smudge filters, textconv and external diff
helpers are never executed. Line-ending/filter normalization can therefore make a file look modified; that
errs toward scanning more, never less.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from ..errors import ApiError
from . import fsread
from .registry import CapturedFile

if TYPE_CHECKING:
    from ..contracts.models import CaptureRequest
    from ..policy.auth import Principal
    from ..services.inputs import InputService
    from .registry import Capture

_BASELINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/~^@{}-]{0,199}$")
MAX_TRACKED_PATHS = 5000
MAX_LISTED_FILES = 200


def _env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
        "LC_ALL": "C",
        "HOME": os.devnull,
    }


def _git(root: Path, *args: str, timeout: float = 20) -> bytes:
    cmd = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=" + os.devnull, "-c", "core.pager=cat",
           "-c", "core.untrackedCache=false", "-c", "protocol.allow=never", "--no-pager",
           "--git-dir", str(root / ".git"), "--work-tree", str(root), *args]
    try:
        r = subprocess.run(cmd, cwd=root, env=_env(), capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ApiError(503, "git_unavailable", "Git could not be run for this workspace.", True)
    if r.returncode != 0:
        raise _GitFailed(r.stderr[:200].decode("utf-8", "replace"))
    return r.stdout


class _GitFailed(Exception):
    pass


def blob_id(data: bytes, algo_len: int) -> str:
    header = b"blob %d\0" % len(data)
    h = hashlib.sha256() if algo_len == 64 else hashlib.sha1()
    h.update(header + data)
    return h.hexdigest()


def resolve_baseline(root: Path, baseline: str) -> str:
    if not _BASELINE.match(baseline) or ".." in baseline or baseline.startswith("-"):
        raise ApiError(422, "invalid_baseline", "Baseline must be a commit name such as HEAD, a branch or a commit ID.")
    try:
        out = _git(root, "rev-parse", "--verify", "--quiet", "--end-of-options", baseline + "^{commit}")
    except _GitFailed:
        raise ApiError(422, "invalid_baseline", "The baseline does not resolve to a commit in this repository.")
    oid = out.decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid):
        raise ApiError(422, "invalid_baseline", "The baseline does not resolve to a commit in this repository.")
    return oid


def _ls_tree(root: Path, commit: str) -> dict[str, tuple[str, str]]:
    out = _git(root, "ls-tree", "-r", "-z", "--full-tree", commit)
    entries: dict[str, tuple[str, str]] = {}
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, _, path = rec.partition(b"\t")
        mode, typ, oid = meta.decode().split(" ")
        if typ == "blob":
            entries[path.decode("utf-8", "surrogateescape")] = (mode, oid)
        if len(entries) > MAX_TRACKED_PATHS:
            raise ApiError(413, "repository_too_large", "Too many tracked files for change capture; select files explicitly.")
    return entries


def _ls_files(root: Path, *flags: str) -> list[str]:
    out = _git(root, "ls-files", "-z", *flags)
    paths = [p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p]
    if len(paths) > MAX_TRACKED_PATHS:
        raise ApiError(413, "repository_too_large", "Too many files for change capture; select files explicitly.")
    return paths


def capture_changes(svc: "InputService", p: "Principal", ws: dict, req: "CaptureRequest") -> "Capture":
    root = Path(ws["root"])
    if not (root / ".git").is_dir() or (root / ".git").is_symlink():
        raise ApiError(422, "not_a_git_repository", "This workspace root is not a Git repository.")
    commit = resolve_baseline(root, req.baseline or "HEAD")
    tree = _ls_tree(root, commit)
    index_paths = set(_ls_files(root, "--cached"))
    untracked = set(_ls_files(root, "--others", "--exclude-standard")) if req.include_untracked else set()
    algo_len = len(commit)
    lim = svc.limits
    changed: list[tuple[str, str]] = []   # (path, change)
    stats: dict[str, tuple] = {}
    data_by_path: dict[str, bytes] = {}
    rejected: list[CapturedFile] = []
    from ..util import new_id

    for path in sorted(set(tree) | index_paths | untracked):
        mode = tree.get(path, ("", ""))[0]
        if mode in ("160000", "120000"):
            continue  # submodules and committed symlinks are not followed
        try:
            rel = fsread.normalize_rel(path)
        except fsread.UnsafePath as ex:
            rejected.append(CapturedFile(new_id("file"), path[:300], "rejected", reason=ex.reason))
            continue
        if fsread.is_excluded(rel, ws["excludes"]):
            if path not in tree and path not in untracked:
                continue
            if path in untracked or path in index_paths:
                rejected.append(CapturedFile(new_id("file"), rel, "rejected", reason="excluded_path"))
            continue
        try:
            rr = fsread.read_file(root, rel, lim.max_file_bytes, ws["excludes"])
        except fsread.UnsafePath as ex:
            if ex.reason == "not_found":
                if path in tree:
                    changed.append((rel, "deleted"))
                continue
            rejected.append(CapturedFile(new_id("file"), rel, "rejected", reason=ex.reason,
                                         change="untracked" if path in untracked else None))
            continue
        if path in tree:
            if blob_id(rr.data, algo_len) == tree[path][1]:
                continue
            change = "modified"
        elif path in untracked:
            change = "untracked"
        else:
            change = "added"
        changed.append((rel, change))
        data_by_path[rel] = rr.data
        stats[rel] = (rr.size, rr.mtime_ns, rr.ino, rr.dev)

    # Pair deletions and additions with identical content as renames.
    deleted = {pth for pth, ch in changed if ch == "deleted"}
    renames: dict[str, str] = {}
    for pth, ch in changed:
        if ch in ("added", "untracked"):
            bid = blob_id(data_by_path[pth], algo_len)
            old = next((d for d in deleted if tree[d][1] == bid and d not in renames.values()), None)
            if old:
                renames[pth] = old
    files: list[CapturedFile] = []
    for pth, ch in changed:
        if ch == "deleted":
            if pth in renames.values():
                continue
            files.append(CapturedFile(new_id("file"), pth, "deleted", change="deleted"))
            continue
        cf = svc.make_file(pth, data_by_path[pth], "renamed" if pth in renames else ch)
        if pth in renames:
            cf.old_path = renames[pth]
        files.append(cf)

    svc.e.hooks.after_read()
    # Concurrent-change detection: identities must be unchanged and the baseline must still resolve the same.
    for f in files:
        if f.status == "captured" and fsread.restat(root, f.path) != stats.get(f.path):
            raise ApiError(409, "capture_conflict", "A changed file was modified during capture; retry the capture.", True)
    if resolve_baseline(root, req.baseline or "HEAD") != commit:
        raise ApiError(409, "capture_conflict", "The baseline moved during capture; retry the capture.", True)

    captured = [f for f in files if f.status == "captured"]
    omitted = ["cross_file_context_not_captured"]
    if len(captured) > lim.max_files_per_capture:
        keep = {f.file_id for f in captured[: lim.max_files_per_capture]}
        for f in captured[lim.max_files_per_capture:]:
            f.status, f.reason, f.data = "rejected", "file_limit", None
        omitted.append(f"{len(captured) - len(keep)}_changed_files_over_limit")
    files = (files + rejected)[:MAX_LISTED_FILES]
    if not files:
        raise ApiError(422, "no_changes", "No saved changes were found against the baseline.")
    return svc.finalize(p, ws["id"], "changes", files, baseline=commit, omitted=omitted)
