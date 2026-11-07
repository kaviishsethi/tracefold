"""Input capture: uploads and registered-workspace file selection. Produces immutable captures."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from ..contracts.enums import Capability, Disclosure
from ..contracts.models import CaptureRequest, CapturedFileOut, InputOut
from ..errors import ApiError, not_found
from ..inputs import fsread, multipart
from ..inputs.classify import check_text, classify
from ..inputs.registry import Capture, CapturedFile
from ..parsing import PARSER_VERSION
from ..policy.auth import Principal
from ..util import canonical, iso, new_id, now, sha256

if TYPE_CHECKING:
    from ..engine import Engine


def file_out(f: CapturedFile, disclosure: Disclosure) -> CapturedFileOut:
    return CapturedFileOut(
        file_id=f.file_id,
        path=f.path if disclosure == Disclosure.full else None,
        status=f.status, reason=f.reason, size=f.size, kind=f.kind, change=f.change,
    )


def input_out(cap: Capture, disclosure: Disclosure) -> InputOut:
    return InputOut(
        input_id=cap.input_id, workspace_id=cap.workspace_id, revision=cap.revision,
        expires_at=iso(cap.expires_at), baseline=cap.baseline,
        files=[file_out(f, disclosure) for f in cap.files], omitted_context=cap.omitted_context,
    )


class InputService:
    def __init__(self, engine: "Engine"):
        self.e = engine

    @property
    def limits(self):
        return self.e.settings.limits

    def _workspace(self, ws_id: str) -> dict:
        ws = self.e.repo.get_workspace(ws_id)
        if ws is None:
            raise not_found()
        return ws

    def make_file(self, path: str, data: bytes, change: str | None = None) -> CapturedFile:
        fid = new_id("file")
        kind, lang = classify(path)
        if kind is None:
            return CapturedFile(fid, path, "rejected", reason="unsupported_type", size=len(data), change=change)
        if len(data) > self.limits.max_file_bytes:
            return CapturedFile(fid, path, "rejected", reason="too_large", size=len(data), change=change)
        if kind in ("text", "code"):
            bad = check_text(data)
            if bad:
                return CapturedFile(fid, path, "rejected", reason=bad, size=len(data), change=change)
        return CapturedFile(fid, path, "captured", data=data, sha256=sha256(data), size=len(data), kind=kind,
                            language=lang, change=change)

    def finalize(self, p: Principal, ws_id: str, source: str, files: list[CapturedFile],
                 baseline: str | None = None, omitted: list[str] | None = None) -> Capture:
        if not files:
            raise ApiError(422, "empty_capture", "No files were selected.")
        if sum(1 for f in files if f.status == "captured") > self.limits.max_files_per_capture or len(files) > 200:
            raise ApiError(413, "too_many_files", f"At most {self.limits.max_files_per_capture} files per capture.")
        captured_text = sum(f.size or 0 for f in files if f.status == "captured")
        if captured_text > self.limits.max_extracted_text_per_capture:
            raise ApiError(413, "capture_too_large", "The selected files exceed the per-capture size limit.")
        digest = sha256(canonical(sorted([[f.path, f.status, f.sha256, f.change] for f in files], key=lambda r: (r[0], r[1]))))
        revision = self.e.repo.bump_revision(ws_id)
        t = now()
        cap = Capture(
            input_id=new_id("input"), workspace_id=ws_id, revision=revision, source=source, files=files,
            manifest_digest=digest, created_at=t, expires_at=t + timedelta(seconds=self.limits.capture_ttl_seconds),
            baseline=baseline, omitted_context=omitted or [],
        )
        self.e.registry.add(cap)
        self.e.repo.insert_input({
            "id": cap.input_id, "workspace_id": ws_id, "revision": revision, "source": source,
            "manifest_digest": digest,
            "files": [{"file_id": f.file_id, "path": f.path, "status": f.status, "sha256": f.sha256, "size": f.size,
                       "kind": f.kind, "language": f.language, "reason": f.reason, "change": f.change, "old_path": f.old_path}
                      for f in files],
            "baseline": baseline, "parser_version": PARSER_VERSION, "created_by": p.client_id,
            "created_at": iso(t), "expires_at": iso(cap.expires_at),
        })
        return cap

    # ---------- uploads ----------
    def upload(self, p: Principal, ws_id: str, content_type: str | None, body: bytes) -> InputOut:
        g = p.require(ws_id, Capability.submit)
        self._workspace(ws_id)
        parts = multipart.parse(content_type, body, self.limits.max_files_per_capture)
        files = [self.make_file(part.filename, part.data) for part in parts if part.filename is not None]
        cap = self.finalize(p, ws_id, "upload", files)
        return input_out(cap, g.disclosure)

    # ---------- registered workspace ----------
    def capture(self, p: Principal, ws_id: str, req: CaptureRequest) -> InputOut:
        g = p.require(ws_id, Capability.submit)
        ws = self._workspace(ws_id)
        if ws["source_type"] != "local_dir" or not ws["root"]:
            raise ApiError(422, "not_a_registered_directory", "This workspace accepts uploads only.")
        if req.mode == "files":
            if not req.paths:
                raise ApiError(422, "paths_required", "Provide one or more workspace-relative paths.")
            cap = self.capture_paths(p, ws, req.paths)
        else:
            from ..inputs.gitcapture import capture_changes  # milestone 4
            cap = capture_changes(self, p, ws, req)
        return input_out(cap, g.disclosure)

    def read_with_check(self, ws: dict, rels: list[str], change: dict[str, str] | None = None) -> list[CapturedFile]:
        """Read each file, then re-verify identity so a concurrent edit yields a conflict, not mixed versions."""
        root = Path(ws["root"])
        files: list[CapturedFile] = []
        stats: dict[str, tuple] = {}
        for rel in rels:
            try:
                norm = fsread.normalize_rel(rel)
                rr = fsread.read_file(root, norm, self.limits.max_file_bytes, ws["excludes"])
            except fsread.UnsafePath as ex:
                files.append(CapturedFile(new_id("file"), rel if len(rel) < 300 else rel[:300], "rejected", reason=ex.reason,
                                          change=(change or {}).get(rel)))
                continue
            stats[norm] = (rr.size, rr.mtime_ns, rr.ino, rr.dev)
            files.append(self.make_file(norm, rr.data, (change or {}).get(rel)))
        self.e.hooks.after_read()
        for f in files:
            if f.status == "captured" and fsread.restat(root, f.path) != stats.get(f.path):
                raise ApiError(409, "capture_conflict", "A selected file changed during capture; retry the capture.", True)
        return files

    def capture_paths(self, p: Principal, ws: dict, paths: list[str]) -> Capture:
        if len(set(paths)) != len(paths):
            raise ApiError(422, "duplicate_paths", "Each path may be selected once.")
        files = self.read_with_check(ws, paths)
        return self.finalize(p, ws["id"], "files", files)
