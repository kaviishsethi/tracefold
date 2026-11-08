"""Scan submission, status, cancellation and ledger reads."""
from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from ..contracts.enums import Capability, Check, PublicMode, ScanState
from ..contracts.models import (
    CoverageEntry, ErrorBody, LedgerEventOut, LedgerPage, ScanAccepted, ScanList, ScanOut, ScanRequest, StageOut,
)
from ..errors import ApiError, not_found
from ..policy.auth import Principal
from ..util import canonical, iso, new_id, now, sha256

if TYPE_CHECKING:
    from ..engine import Engine


ASSISTANT_HINTS = ("assistant", "mcp")
APP_HINTS = ("web-app", "upload-app", "app")


def started_from(client_name: str | None) -> str:
    """Where a scan came from, by the client's provisioned name (quickstart: web-app-*, coding-assistant-*)."""
    n = (client_name or "").lower()
    if any(h in n for h in ASSISTANT_HINTS):
        return "assistant"
    if any(n.startswith(h) for h in APP_HINTS):
        return "app"
    return "other"


def status_url(ws_id: str, scan_id: str) -> str:
    return f"/v1/workspaces/{ws_id}/scans/{scan_id}"


class ScanService:
    def __init__(self, engine: "Engine"):
        self.e = engine

    def _scan_in_ws(self, ws_id: str, scan_id: str) -> dict:
        s = self.e.repo.get_scan(scan_id)
        if s is None or s["workspace_id"] != ws_id:
            raise not_found()
        return s

    def resolve_input(self, ws_id: str, input_id: str):
        meta = self.e.repo.get_input(input_id)
        if meta is None or meta["workspace_id"] != ws_id:
            raise not_found()
        cap = self.e.registry.get(input_id)
        if cap is None:
            raise ApiError(410, "input_expired", "This input has expired; upload or capture it again to scan it.")
        return meta, cap

    def submit(self, p: Principal, ws_id: str, req: ScanRequest, idem_key: str | None,
               recheck_of: str | None = None, recheck_id: str | None = None,
               scope_paths: list[str] | None = None, explicit_sources: list[dict] | None = None) -> ScanAccepted:
        p.require(ws_id, Capability.submit)
        if self.e.repo.get_workspace(ws_id) is None:
            raise not_found()
        checks = sorted(set(req.checks), key=lambda c: c.value)
        public_sources = req.public_sources.model_dump(mode="json") if req.public_sources else None
        if explicit_sources:  # internal: recheck of a discovered exposure fetches the cited URL explicitly
            public_sources = {"manifest_id": None, "mode": PublicMode.refresh.value, "snapshot_id": None,
                              "source_ids": None, "explicit_sources": explicit_sources}
        public_discovery = req.public_discovery.model_dump(mode="json") if req.public_discovery else None
        payload = {"input_id": req.input_id, "checks": [c.value for c in checks],
                   "public_sources": public_sources, "public_discovery": public_discovery,
                   "review_profile": req.review_profile, "model_review": req.model_review, "recheck_of": recheck_of,
                   "scope_paths": scope_paths}
        digest = sha256(canonical(payload))
        if idem_key:
            if len(idem_key) > 200:
                raise ApiError(422, "invalid_idempotency_key", "Idempotency-Key is too long.")
            prior = self.e.repo.find_idempotent(p.client_id, ws_id, idem_key)
            if prior:
                if prior["request_digest"] != digest:
                    raise ApiError(409, "idempotency_conflict", "This Idempotency-Key was used with a different request.")
                return ScanAccepted(scan_id=prior["id"], state=ScanState(prior["state"]), input_id=prior["input_id"],
                                    status_url=status_url(ws_id, prior["id"]))
        meta, _cap = self.resolve_input(ws_id, req.input_id)
        if Check.public_match in checks and explicit_sources:
            pass
        elif Check.public_match in checks and req.public_discovery is not None:
            if req.public_sources is not None:
                raise ApiError(422, "public_input_conflict", "Use exactly one of public_sources or public_discovery.")
            self.e.discovery.validate_scan_request(ws_id, req.public_discovery)
        elif Check.public_match in checks:
            ps = req.public_sources
            if ps is None:
                raise ApiError(422, "public_sources_required",
                               "public_match requires public_sources.manifest_id or public_discovery.query_plan_id.")
            manifest = self.e.repo.get_manifest(ws_id, ps.manifest_id)
            if manifest is None:
                raise not_found()
            known = {s["source_id"] for s in manifest["sources"]}
            if ps.source_ids and not set(ps.source_ids) <= known:
                raise ApiError(422, "unknown_source", "Only operator-approved source IDs from the manifest may be requested.")
            if ps.mode == PublicMode.snapshot:
                snap = self.e.repo.get_snapshot(ps.snapshot_id or "") if ps.snapshot_id else None
                if snap is None or snap["workspace_id"] != ws_id or snap["manifest_id"] != ps.manifest_id:
                    raise ApiError(422, "snapshot_required", "snapshot mode requires a known snapshot_id for this manifest.")
        elif req.public_sources is not None or req.public_discovery is not None:
            raise ApiError(422, "public_sources_unexpected",
                           "public_sources and public_discovery are only valid with the public_match check.")
        if self.e.repo.count_queued() >= self.e.settings.limits.max_queued_scans:
            raise ApiError(429, "queue_full", "The scan queue is full; retry after current scans finish.", True)
        if self.e.registry.pin(req.input_id) is None:
            raise ApiError(410, "input_expired", "This input has expired; upload or capture it again to scan it.")
        scan_id = new_id("scan")
        t = now()
        try:
            self.e.repo.insert_scan({
                "id": scan_id, "workspace_id": ws_id, "input_id": req.input_id, "revision": meta["revision"],
                "checks": [c.value for c in checks],
                "public_sources": payload["public_sources"], "public_discovery": public_discovery,
                "review_profile": req.review_profile,
                "model_review": int(req.model_review), "recheck_of": recheck_of, "recheck_id": recheck_id,
                "state": ScanState.queued.value, "initiator": p.client_id, "idempotency_key": idem_key,
                "request_digest": digest, "created_at": iso(t),
                "deadline_at": None, "summary": {"scope_paths": scope_paths} if scope_paths else {},
            })
            if recheck_id:
                obs = self.e.repo.observations_for_finding(recheck_of)
                self.e.repo.insert_recheck({
                    "id": recheck_id, "workspace_id": ws_id, "finding_id": recheck_of,
                    "observation_id": obs[-1]["id"] if obs else "", "scan_id": scan_id, "outcome": None,
                    "reason": None, "created_at": iso(t)})
        except Exception:
            self.e.registry.unpin(req.input_id, consumed=False)
            raise
        self.e.runner.wake()
        return ScanAccepted(scan_id=scan_id, state=ScanState.queued, input_id=req.input_id, status_url=status_url(ws_id, scan_id))

    def to_out(self, s: dict) -> ScanOut:
        client = self.e.repo.get_client(s["initiator"]) if s.get("initiator") else None
        name = client["name"] if client else None
        return ScanOut(
            scan_id=s["id"], workspace_id=s["workspace_id"], input_id=s["input_id"], state=ScanState(s["state"]),
            checks=[Check(c) for c in s["checks"]], recheck_of=s["recheck_of"],
            public_snapshot_id=s["public_snapshot_id"], public_freshness=(s["summary"] or {}).get("public_freshness"),
            public_discovery=({**s["public_discovery"], **((s["summary"] or {}).get("discovery") or {})}
                              if s.get("public_discovery") else None),
            stages=[StageOut(**x) for x in s["stages"]], coverage=[CoverageEntry(**x) for x in s["coverage"]],
            budget=s["budget"], versions=s["versions"], errors=[ErrorBody(**x) for x in s["errors"]],
            summary=s["summary"], created_at=s["created_at"], started_at=s["started_at"],
            finished_at=s["finished_at"], deadline_at=s["deadline_at"],
            initiated_by=name, started_from=started_from(name),
        )

    def list(self, p: Principal, ws_id: str, cursor: str | None, limit: int) -> ScanList:
        """Recent scans in the workspace from every client (web app, coding assistant, CLI), newest first."""
        p.require(ws_id, Capability.read)
        limit = max(1, min(limit, self.e.settings.limits.page_size_max))
        rows = self.e.repo.list_scans(ws_id, cursor, limit + 1)
        return ScanList(items=[self.to_out(r) for r in rows[:limit]],
                        next_cursor=rows[limit - 1]["created_at"] if len(rows) > limit else None)

    def get(self, p: Principal, ws_id: str, scan_id: str) -> ScanOut:
        p.require(ws_id, Capability.read)
        return self.to_out(self._scan_in_ws(ws_id, scan_id))

    def cancel(self, p: Principal, ws_id: str, scan_id: str) -> ScanOut:
        p.require(ws_id, Capability.cancel)
        s = self._scan_in_ws(ws_id, scan_id)
        st = self.e.repo.request_cancel(s["id"])
        if st == "cancelled" and s["state"] == "queued":
            self.e.registry.unpin(s["input_id"], consumed=True)
            if s["recheck_id"]:
                self.e.repo.update_recheck(s["recheck_id"], "inconclusive", "scan_cancelled")
        return self.to_out(self.e.repo.get_scan(scan_id))

    def ledger(self, p: Principal, ws_id: str, scan_id: str, cursor: str | None, limit: int) -> LedgerPage:
        p.require(ws_id, Capability.read)
        self._scan_in_ws(ws_id, scan_id)
        limit = max(1, min(limit, self.e.settings.limits.page_size_max))
        rows = self.e.repo.ledger_for_scan(scan_id, cursor, limit + 1)
        items = [LedgerEventOut(event_id=r["id"], scan_id=r["scan_id"], destination_category=r["destination_category"],
                                destination_host=r["destination_host"], purpose=r["purpose"], source_id=r["source_id"],
                                status=r["status"], payload_summary=r["payload_summary"], at=r["at"]) for r in rows[:limit]]
        return LedgerPage(items=items, next_cursor=rows[limit - 1]["id"] if len(rows) > limit else None)
