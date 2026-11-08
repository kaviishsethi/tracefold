"""Public retrieval orchestration: manifest resolution, snapshot creation/reuse and blob storage.

Only operator-approved manifest entries (source IDs → URLs) are ever passed to retrieval. Private text,
filenames and document-derived terms never enter a retrieval request.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts.enums import CoverageStatus, PublicMode
from ..util import iso, new_id, now
from .blobs import BlobStore

if TYPE_CHECKING:
    from ..engine import Engine
    from ..jobs.pipeline import ScanContext


class RetrievalService:
    def __init__(self, engine: "Engine"):
        self.e = engine
        self.blobs = BlobStore(engine.settings.blob_dir, engine.settings.limits.max_public_cache_bytes)

    @staticmethod
    def sandbox_available() -> bool:
        import shutil
        import sys
        return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None

    def deny_paths(self, ctx: "ScanContext") -> tuple[list[str], bool]:
        """Private locations the worker must not read. Paths that contain the interpreter, the engine code or the
        public fixture root cannot be denied without breaking the worker; that degrades isolation and is reported."""
        import os
        import sys
        from pathlib import Path
        needed = [Path(sys.prefix).resolve(), Path(__file__).resolve().parents[1]]
        if self.e.settings.fixture_root:
            needed.append(Path(self.e.settings.fixture_root).resolve())
        candidates = [self.e.settings.data_dir]
        ws = self.e.repo.get_workspace(ctx.scan["workspace_id"])
        if ws and ws["root"]:
            candidates.append(Path(ws["root"]))
        deny, degraded = [], False
        for c in candidates:
            c = Path(os.path.realpath(c))
            if any(c == n or c in n.parents for n in needed):
                degraded = True
                continue
            deny.append(str(c))
        return deny, degraded

    def build_request(self, ctx: "ScanContext", sources: list[dict]) -> dict:
        lim = self.e.settings.limits
        return {
            "sources": [{k: s[k] for k in ("source_id", "url", "provider", "fixture_path") if k in s} for s in sources],
            "limits": {"max_text": lim.max_public_text_per_page, "max_raw": lim.max_public_raw_bytes_per_page,
                       "max_requests": lim.max_provider_requests, "concurrency": lim.public_http_concurrency},
            "deadline_seconds": max(1.0, min(ctx.remaining_seconds() - 5, 120.0)),
            "fixture_root": str(self.e.settings.fixture_root) if self.e.settings.fixture_root else None,
        }

    def call_worker(self, ctx: "ScanContext", req: dict) -> dict:
        """Run one worker operation (fetch or search) in the isolated worker; record its ledger and request spend."""
        from .worker import run_request, run_subprocess
        if self.e.settings.retrieval_in_process:
            resp = run_request(req, transport=getattr(self.e, "test_transport", None),
                               resolver=getattr(self.e, "test_resolver", None), env=getattr(self.e, "test_env", None))
            ctx.summary["retrieval_isolation"] = "in_process_test_mode"
        else:
            deny, degraded = self.deny_paths(ctx)
            resp = run_subprocess(req, timeout=req["deadline_seconds"] + 10, deny_read=deny)
            ctx.summary["retrieval_isolation"] = "separate_process" + ("_sandboxed" if self.sandbox_available() else "") + \
                ("_partial" if degraded else "")
        for ev in resp.get("ledger", []):
            ctx.ledger.append({**ev, "scan_id": ctx.scan_id, "workspace_id": ctx.scan["workspace_id"]})
        ctx.spend("provider_requests", resp.get("requests", 0))
        return resp

    def fetch(self, ctx: "ScanContext", sources: list[dict]) -> list[dict]:
        return self.call_worker(ctx, self.build_request(ctx, sources))["results"]

    def run(self, ctx: "ScanContext") -> None:
        ps = ctx.scan["public_sources"]
        ws_id = ctx.scan["workspace_id"]
        if ps.get("explicit_sources"):
            # Recheck of a discovered exposure: fetch the previously cited URL explicitly (never via a new search).
            manifest = {"id": f"recheck:{ctx.scan_id}", "version": 1, "sources": ps["explicit_sources"]}
        else:
            manifest = self.e.repo.get_manifest(ws_id, ps["manifest_id"])
        if manifest is None:
            raise RuntimeError("manifest missing")
        wanted = ps.get("source_ids")
        sources = [s for s in manifest["sources"] if not wanted or s["source_id"] in wanted]
        limit = self.e.settings.limits.max_public_pages
        omitted = sources[limit:]
        sources = sources[:limit]
        for s in omitted:
            ctx.cover("source", s["source_id"], CoverageStatus.not_requested, "page_limit")

        if ps["mode"] == PublicMode.snapshot.value:
            snap = self.e.repo.get_snapshot(ps["snapshot_id"])
            entries = []
            for s in snap["sources"]:
                if wanted and s["source_id"] not in wanted:
                    continue
                entries.append({**s, "freshness": "cached"})
            ctx.summary["public_freshness"] = f"cached snapshot from {snap['created_at']}"
            snap_id = snap["id"]
        else:
            results = self.fetch(ctx, sources)
            entries = []
            for r in results:
                entry = {"source_id": r["source_id"], "url": r["url"], "final_url": r.get("final_url"),
                         "provider": r.get("provider"), "status": r["status"], "error": r.get("error"),
                         "retrieved_at": r.get("retrieved_at"), "truncated": r.get("truncated", False),
                         "content_hash": None, "chars": 0, "freshness": "fresh", "mode": "seeded"}
                if ps.get("explicit_sources"):
                    entry.update(mode="discovered", recheck=True)
                if r["status"] == "ok":
                    entry["content_hash"] = self.blobs.put(r["text"])
                    entry["chars"] = len(r["text"])
                entries.append(entry)
            snap_id = new_id("snap")
            self.e.repo.insert_snapshot({"id": snap_id, "workspace_id": ws_id, "manifest_id": manifest["id"],
                                         "manifest_version": manifest["version"], "sources": entries,
                                         "created_at": iso(now())})
            ctx.summary["public_freshness"] = "fresh retrieval"
            self.blobs.gc(self.e.repo.referenced_blob_hashes())
        ctx.public_snapshot = {"id": snap_id, "sources": entries}
        ctx.engine.repo.update_scan(ctx.scan_id, public_snapshot_id=snap_id)
        ok = 0
        for en in entries:
            text = self.blobs.read(en["content_hash"]) if en.get("status") == "ok" and en.get("content_hash") else None
            if text is None:
                ctx.cover("source", en["source_id"], CoverageStatus.failed, en.get("error") or "unavailable")
                continue
            ctx.public_texts[en["source_id"]] = text
            ok += 1
            ctx.cover("source", en["source_id"], CoverageStatus.partial if en.get("truncated") else CoverageStatus.complete,
                      "truncated" if en.get("truncated") else None, chars=en.get("chars", 0))
        ctx.summary["public_sources_ok"] = ok
        ctx.summary["public_sources_requested"] = len(entries)
