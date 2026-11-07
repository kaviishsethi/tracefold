"""Versioned findings store: correlation, observation history and revision-guarded current status."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts.enums import FindingStatus
from ..jobs.model import Proposed
from ..util import iso, new_id, now, sha256

if TYPE_CHECKING:
    from ..engine import Engine

OBS_FIELDS = ("check_version", "rule_id", "origin", "title", "claim", "conditions", "missing_context", "uncertainty",
              "suggested_fix", "verification_step", "severity", "severity_rationale", "risk_review", "counterevidence",
              "model_id", "prompt_version", "source_id")


def file_key(path: str) -> str:
    return sha256("file:" + path)


def correlation_key(p: Proposed) -> str:
    # Conservative: same workspace (enforced by the unique index), file identity, check, rule and evidence anchor.
    return sha256("|".join([p.kind, p.check_id, p.rule_id or "", file_key(p.file.path), p.source_id or "", p.anchor]))


class FindingStore:
    def __init__(self, engine: "Engine"):
        self.e = engine

    def publish(self, scan: dict, proposals: list[Proposed]) -> list[tuple[str, str]]:
        """Persist observations transactionally. Returns [(finding_id, observation_id)]."""
        repo = self.e.repo
        out: list[tuple[str, str]] = []
        t = iso(now())
        with repo.db.tx():
            for p in proposals:
                key = correlation_key(p)
                f = repo.get_finding_by_key(scan["workspace_id"], key)
                if f is None:
                    fid = new_id("fnd")
                    repo.insert_finding({
                        "id": fid, "workspace_id": scan["workspace_id"], "kind": p.kind, "check_id": p.check_id,
                        "rule_id": p.rule_id, "correlation_key": key, "file_key": file_key(p.file.path), "path": p.file.path,
                        "status": FindingStatus.open.value, "status_revision": scan["revision"],
                        "first_seen_scan": scan["id"], "last_seen_scan": scan["id"], "created_at": t, "updated_at": t,
                    })
                else:
                    fid = f["id"]
                    if scan["revision"] >= f["status_revision"]:
                        repo.update_finding(fid, status=FindingStatus.open.value, status_revision=scan["revision"],
                                            last_seen_scan=scan["id"], updated_at=t)
                    # else: a stale scan only adds history; it cannot change the current view.
                ev_ids = []
                for ev in p.evidence:
                    eid = new_id("evd")
                    repo.insert_evidence({"id": eid, "workspace_id": scan["workspace_id"], "scan_id": scan["id"],
                                          "input_id": scan["input_id"], "data": ev})
                    ev_ids.append(eid)
                oid = new_id("obs")
                data = {k: getattr(p, k) for k in OBS_FIELDS}
                data.update({"kind": p.kind, "check_id": p.check_id, "evidence_ids": ev_ids, "file_id": p.file.file_id,
                             "path": p.file.path})
                repo.insert_observation({"id": oid, "finding_id": fid, "scan_id": scan["id"], "input_id": scan["input_id"],
                                         "revision": scan["revision"], "data": data, "created_at": t})
                out.append((fid, oid))
        return out

    def set_status(self, finding_id: str, status: FindingStatus, revision: int, allow_equal: bool = False) -> bool:
        """Revision-guarded status change. Returns False if a newer revision already owns the status."""
        repo = self.e.repo
        with repo.db.tx():
            f = repo.get_finding(finding_id)
            if f is None or revision < f["status_revision"] or (revision == f["status_revision"] and not allow_equal):
                return False
            repo.update_finding(finding_id, status=status.value, status_revision=revision, updated_at=iso(now()))
            return True
