"""Findings, evidence, human review and recheck submission."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..contracts.enums import (
    Capability, Check, Disclosure, FindingKind, FindingStatus, HumanReview, Origin, PublicMode, RiskReview,
)
from ..contracts.models import (
    EvidenceOut, FindingDetail, FindingOut, FindingPage, LocationOut, ObservationOut, PublicSpanOut,
    RecheckAccepted, RecheckOut, RecheckRequest, ReviewRequest, ScanRequest, PublicSourcesIn,
)
from ..errors import ApiError, not_found
from ..policy.auth import Principal
from ..util import iso, new_id, now

if TYPE_CHECKING:
    from ..engine import Engine

MASK = "•"


CONTEXT = 80  # characters of surrounding text shown on each side of a cited span


def mask_text(text: str, spans: list[list[int]], base: int) -> str:
    chars = list(text)
    for s, e in spans:
        for i in range(max(s - base, 0), min(e - base, len(chars))):
            if not chars[i].isspace():
                chars[i] = MASK
    return "".join(chars)


class FindingService:
    def __init__(self, engine: "Engine"):
        self.e = engine

    # ---------- shaping ----------
    def _finding_in_ws(self, ws_id: str, finding_id: str) -> dict:
        f = self.e.repo.get_finding(finding_id)
        if f is None or f["workspace_id"] != ws_id:
            raise not_found()
        return f

    def evidence_out(self, ev: dict, disclosure: Disclosure, include_text: bool = False) -> EvidenceOut:
        d = ev["data"]
        loc = dict(d["location"])
        out = EvidenceOut(
            evidence_id=ev["id"], scan_id=ev["scan_id"], kind=d["kind"],
            location=LocationOut(
                file_id=loc["file_id"], path=loc["path"] if disclosure == Disclosure.full else None,
                start=loc["start"], end=loc["end"], line_start=loc.get("line_start"), line_end=loc.get("line_end"),
                paragraph_id=loc.get("paragraph_id"),
            ),
            file_sha256_prefix=(d.get("file_sha256") or "")[:12],
            public=PublicSpanOut(**d["public"]) if d.get("public") else None,
            rule_id=d.get("rule_id"), matched_tokens=d.get("matched_tokens"), segment_coverage=d.get("segment_coverage"),
        )
        if include_text:
            if disclosure != Disclosure.full:
                out.availability = "withheld_by_policy"
            else:
                local = self._local_text(ev)
                out.local_text = local
                out.public_text = self._public_text(d)
                out.availability = "available" if local is not None else "evidence_unavailable"
                s, e = loc["start"], loc["end"]
                if local is not None:
                    out.local_highlight = [s - max(0, s - CONTEXT), e - max(0, s - CONTEXT)]
                pub = d.get("public")
                if out.public_text is not None and pub:
                    ps = max(0, pub["start"] - CONTEXT)
                    out.public_highlight = [pub["start"] - ps, min(pub["end"], ps + len(out.public_text)) - ps]
        return out

    def _local_text(self, ev: dict) -> str | None:
        """Historical evidence text only from bytes whose hash matches the scanned file; never current text."""
        d = ev["data"]
        loc = d["location"]
        want = d.get("file_sha256")
        data: bytes | None = None
        cap = self.e.registry.get(ev["input_id"])
        if cap:
            f = cap.file(loc["file_id"])
            if f and f.data is not None and f.sha256 == want:
                data = f.data
        if data is None:
            meta = self.e.repo.get_input(ev["input_id"])
            ws = self.e.repo.get_workspace(ev["workspace_id"])
            if meta and ws and ws["root"] and meta["source"] in ("files", "changes"):
                from ..inputs import fsread
                from ..util import sha256
                try:
                    rr = fsread.read_file(Path(ws["root"]), loc["path"], self.e.settings.limits.max_file_bytes, ws["excludes"])
                    if sha256(rr.data) == want:
                        data = rr.data
                except fsread.UnsafePath:
                    data = None
        if data is None:
            return None
        from ..inputs.registry import CapturedFile
        from ..parsing.document import parse_text
        cf = CapturedFile(loc["file_id"], loc["path"], "captured", data=data, sha256=want, kind=d.get("file_kind"))
        if d.get("file_kind") == "docx":
            from ..parsing.docx import parse_docx
            doc = parse_docx(cf, self.e.settings.limits)
        else:
            doc = parse_text(cf)
        s, e = loc["start"], loc["end"]
        cs, ce = max(0, s - CONTEXT), min(len(doc.text), e + CONTEXT)
        return mask_text(doc.text[cs:ce], d.get("mask_spans", []), cs)

    def _public_text(self, d: dict) -> str | None:
        pub = d.get("public")
        if not pub or not d.get("public_blob"):
            return None
        text = self.e.retrieval.blobs.read(d["public_blob"])
        if text is None:
            return None
        return text[max(0, pub["start"] - CONTEXT): pub["end"] + CONTEXT]

    def obs_out(self, o: dict, disclosure: Disclosure) -> ObservationOut:
        d = o["data"]
        evs = [self.e.repo.get_evidence(eid) for eid in d.get("evidence_ids", [])]
        minimal = disclosure != Disclosure.full
        model_text = d.get("origin") == Origin.model.value or d.get("risk_review") not in (None, "not_requested", "unavailable")
        return ObservationOut(
            observation_id=o["id"], finding_id=o["finding_id"], scan_id=o["scan_id"], input_id=o["input_id"],
            revision=o["revision"], origin=Origin(d["origin"]), check_id=d["check_id"], check_version=d["check_version"],
            rule_id=d.get("rule_id"), title=d["title"],
            claim=None if minimal else d.get("claim"),
            conditions=None if minimal else d.get("conditions"),
            missing_context=None if minimal else d.get("missing_context"),
            uncertainty=d.get("uncertainty"),
            suggested_fix=None if (minimal and model_text) else d.get("suggested_fix"),
            verification_step=d.get("verification_step"),
            severity=d.get("severity"), severity_rationale=None if minimal else d.get("severity_rationale"),
            risk_review=RiskReview(d.get("risk_review") or "not_requested"),
            counterevidence=None if minimal else d.get("counterevidence"),
            model_id=d.get("model_id"), prompt_version=d.get("prompt_version"),
            evidence=[self.evidence_out(ev, disclosure) for ev in evs if ev],
            created_at=o["created_at"],
        )

    def finding_out(self, f: dict, disclosure: Disclosure, scan_id: str | None = None) -> FindingOut:
        obs = self.e.repo.observations_for_finding(f["id"], scan_id)
        return FindingOut(
            finding_id=f["id"], workspace_id=f["workspace_id"], kind=FindingKind(f["kind"]), check_id=f["check_id"],
            rule_id=f["rule_id"], status=FindingStatus(f["status"]), human_review=HumanReview(f["human_review"]),
            human_review_reason=f["human_review_reason"], version=f["version"],
            path=f["path"] if disclosure == Disclosure.full else None,
            first_seen_scan=f["first_seen_scan"], last_seen_scan=f["last_seen_scan"], current_revision=f["status_revision"],
            latest=self.obs_out(obs[-1], disclosure) if obs else None,
        )

    # ---------- reads ----------
    def list(self, p: Principal, ws_id: str, scan_id: str | None, cursor: str | None, limit: int) -> FindingPage:
        g = p.require(ws_id, Capability.read)
        if scan_id:
            s = self.e.repo.get_scan(scan_id)
            if s is None or s["workspace_id"] != ws_id:
                raise not_found()
        limit = max(1, min(limit, self.e.settings.limits.page_size_max))
        rows = self.e.repo.list_findings(ws_id, scan_id, cursor, limit + 1)
        items = [self.finding_out(f, g.disclosure, scan_id) for f in rows[:limit]]
        return FindingPage(items=items, next_cursor=rows[limit - 1]["id"] if len(rows) > limit else None)

    def detail(self, p: Principal, ws_id: str, finding_id: str) -> FindingDetail:
        g = p.require(ws_id, Capability.read)
        f = self._finding_in_ws(ws_id, finding_id)
        base = self.finding_out(f, g.disclosure)
        obs = [self.obs_out(o, g.disclosure) for o in self.e.repo.observations_for_finding(f["id"])]
        rcs = [RecheckOut(recheck_id=r["id"], finding_id=r["finding_id"], observation_id=r["observation_id"],
                          scan_id=r["scan_id"], outcome=r["outcome"], reason=r["reason"], created_at=r["created_at"])
               for r in self.e.repo.rechecks_for_finding(f["id"])]
        return FindingDetail(**base.model_dump(), observations=obs, rechecks=rcs)

    def evidence(self, p: Principal, ws_id: str, evidence_id: str) -> EvidenceOut:
        g = p.require(ws_id, Capability.read_evidence)
        ev = self.e.repo.get_evidence(evidence_id)
        if ev is None or ev["workspace_id"] != ws_id:
            raise not_found()
        return self.evidence_out(ev, g.disclosure, include_text=True)

    # ---------- mutations ----------
    def review(self, p: Principal, ws_id: str, finding_id: str, req: ReviewRequest) -> FindingOut:
        g = p.require(ws_id, Capability.review)
        f = self._finding_in_ws(ws_id, finding_id)
        if req.state == HumanReview.dismissed and not (req.reason and req.reason.strip()):
            raise ApiError(422, "reason_required", "Dismissal requires a reason; evidence is retained.")
        if not self.e.repo.update_finding_review(f["id"], req.state.value, req.reason, req.expected_version):
            raise ApiError(409, "version_conflict", "The finding changed; reload it and retry.")
        return self.finding_out(self.e.repo.get_finding(f["id"]), g.disclosure)

    def recheck(self, p: Principal, ws_id: str, finding_id: str, req: RecheckRequest, idem_key: str | None) -> RecheckAccepted:
        p.require(ws_id, Capability.recheck)
        p.require(ws_id, Capability.submit)
        f = self._finding_in_ws(ws_id, finding_id)
        obs_all = self.e.repo.observations_for_finding(f["id"])
        if req.observation_id:
            target = next((o for o in obs_all if o["id"] == req.observation_id), None)
            if target is None:
                raise not_found()
        else:
            target = obs_all[-1]
        public_sources = None
        explicit = None
        if f["kind"] == FindingKind.public_exposure.value:
            prior = self.e.repo.get_scan(target["scan_id"])
            ps = prior["public_sources"] or {}
            sid = target["data"]["source_id"]
            if prior.get("public_discovery") or ps.get("explicit_sources"):
                # Discovered exposure: recheck fetches the previously cited URL explicitly. Current search results
                # are not consulted, so omission from search cannot resolve it.
                snap = self.e.repo.get_snapshot(prior["public_snapshot_id"]) if prior["public_snapshot_id"] else None
                src = next((x for x in (snap or {}).get("sources", []) if x["source_id"] == sid), None)
                if src is None:
                    raise ApiError(409, "recheck_source_unavailable", "The cited public source is no longer recorded.")
                explicit = [{"source_id": sid, "url": src["url"], "provider": src.get("provider") or "direct",
                             "mode": "discovered"}]
            else:
                public_sources = PublicSourcesIn(manifest_id=ps["manifest_id"], mode=PublicMode.refresh, source_ids=[sid])
        rid = new_id("rck")
        sreq = ScanRequest(input_id=req.input_id, checks=[Check(f["check_id"])], public_sources=public_sources, model_review=False)
        acc = self.e.scans.submit(p, ws_id, sreq, idem_key, recheck_of=f["id"], recheck_id=rid,
                                  scope_paths=[f["path"]], explicit_sources=explicit)
        if self.e.repo.get_recheck(rid) is None:
            prior_scan = self.e.repo.get_scan(acc.scan_id)
            rid = prior_scan["recheck_id"]  # idempotent replay
        return RecheckAccepted(recheck_id=rid, scan_id=acc.scan_id, state=acc.state, status_url=acc.status_url)
