"""Scan pipeline: parse → (public retrieval → exact match) ‖ local rules → model review → validate → publish.

Stage failures are isolated: a retrieval failure cannot disable local rules, and a model failure cannot
delete deterministic matches. Cancellation and the deadline are checked between units of work.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable

from ..contracts.enums import Check, CoverageStatus, ScanState
from ..util import iso, now

if TYPE_CHECKING:
    from ..engine import Engine
    from ..inputs.registry import Capture

log = logging.getLogger("tracefold.pipeline")

ENGINE_VERSION = "0.1.0"


class Cancelled(Exception):
    pass


class DeadlineExceeded(Exception):
    pass


@dataclass
class ScanContext:
    engine: "Engine"
    scan: dict
    capture: "Capture"
    deadline: datetime
    stages: list[dict] = field(default_factory=list)
    coverage: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    budget: dict[str, int] = field(default_factory=dict)
    versions: dict[str, str] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    docs: list = field(default_factory=list)            # ParsedDoc
    candidates: list = field(default_factory=list)      # ProposedObservation
    public_snapshot: dict | None = None
    public_texts: dict[str, str] = field(default_factory=dict)  # source_id -> text
    ledger: list[dict] = field(default_factory=list)

    @property
    def scan_id(self) -> str:
        return self.scan["id"]

    @property
    def checks(self) -> set[str]:
        return set(self.scan["checks"])

    def checkpoint(self) -> None:
        if self.engine.repo.cancel_requested(self.scan_id):
            raise Cancelled()
        if now() >= self.deadline:
            raise DeadlineExceeded()

    def remaining_seconds(self) -> float:
        return max(0.0, (self.deadline - now()).total_seconds())

    def cover(self, scope: str, id_: str, status: CoverageStatus, reason: str | None = None, **counts: int) -> None:
        self.coverage = [c for c in self.coverage if not (c["scope"] == scope and c["id"] == id_)]
        self.coverage.append({"scope": scope, "id": id_, "status": status.value, "reason": reason, "counts": counts})

    def error(self, code: str, message: str, retryable: bool = False) -> None:
        self.errors.append({"code": code, "message": message, "retryable": retryable})

    def spend(self, key: str, n: int = 1) -> None:
        self.budget[key] = self.budget.get(key, 0) + n

    def persist(self) -> None:
        self.engine.repo.update_scan(self.scan_id, stages=self.stages, coverage=self.coverage, errors=self.errors,
                                     budget=self.budget, versions=self.versions, summary=self.summary)

    @contextmanager
    def stage(self, name: str):
        st = next(s for s in self.stages if s["name"] == name)
        st["status"] = "running"
        self.persist()
        self.engine.hooks.before_stage(self, name)
        try:
            yield st
        except Cancelled:
            st["status"] = "cancelled"
            raise
        except DeadlineExceeded:
            st["status"] = "failed"
            st["detail"] = "deadline_exceeded"
            raise
        except Exception as ex:
            log.warning("stage %s failed: %s", name, type(ex).__name__)
            st["status"] = "failed"
            st["detail"] = st.get("detail") or type(ex).__name__
            raise
        else:
            if st["status"] == "running":
                st["status"] = "done"
        finally:
            self.persist()


def plan_stages(scan: dict) -> list[str]:
    checks = set(scan["checks"])
    names = ["parse"]
    if Check.public_match.value in checks:
        names += ["public_retrieval", "public_match"]
    if Check.local_risk.value in checks:
        names += ["local_rules"]
        if scan["model_review"]:
            names += ["model_review"]
    names += ["publish"]
    return names


def _final_state(ctx: ScanContext) -> ScanState:
    requested = [c for c in ctx.coverage if c["scope"] in ("check",) and c["status"] != CoverageStatus.not_requested.value]
    if not requested:
        return ScanState.failed
    statuses = {c["status"] for c in requested}
    file_bad = any(c["scope"] == "file" and c["status"] != CoverageStatus.complete.value for c in ctx.coverage)
    if statuses == {CoverageStatus.failed.value}:
        return ScanState.failed
    if statuses == {CoverageStatus.complete.value} and not file_bad:
        return ScanState.completed
    return ScanState.partial


def run_scan(engine: "Engine", scan: dict) -> None:
    from . import stages as S

    capture = engine.registry.get(scan["input_id"])
    deadline = now() + timedelta(seconds=engine.settings.limits.scan_deadline_seconds)
    engine.repo.update_scan(scan["id"], deadline_at=iso(deadline))
    if capture is None:
        engine.repo.update_scan(
            scan["id"], state=ScanState.failed.value, finished_at=iso(now()),
            errors=[{"code": "input_expired", "message": "The captured input expired before the scan ran; capture it again.", "retryable": False}],
        )
        if scan["recheck_id"]:
            engine.repo.update_recheck(scan["recheck_id"], "inconclusive", "input_expired")
        return

    ctx = ScanContext(engine=engine, scan=scan, capture=capture, deadline=deadline, summary=dict(scan.get("summary") or {}))
    ctx.stages = [{"name": n, "status": "pending", "detail": None} for n in plan_stages(scan)]
    ctx.versions = {"engine": ENGINE_VERSION, **S.versions(engine)}
    for chk in (Check.public_match, Check.local_risk):
        if chk.value not in ctx.checks:
            ctx.cover("check", chk.value, CoverageStatus.not_requested)
    final: ScanState | None = None
    steps: list[tuple[str, Callable[[ScanContext], None]]] = [
        ("parse", S.parse_stage),
        ("public_retrieval", S.public_retrieval_stage),
        ("public_match", S.public_match_stage),
        ("local_rules", S.local_rules_stage),
        ("model_review", S.model_review_stage),
    ]
    try:
        for name, fn in steps:
            if any(s["name"] == name for s in ctx.stages):
                ctx.checkpoint()
                try:
                    with ctx.stage(name):
                        fn(ctx)
                except (Cancelled, DeadlineExceeded):
                    raise
                except Exception:
                    ctx.error(f"{name}_failed", f"The {name.replace('_', ' ')} stage failed; other stages continue.", True)
                    S.on_stage_failure(ctx, name)
    except Cancelled:
        final = ScanState.cancelled
        ctx.error("cancelled", "The scan was cancelled; completed observations are retained as partial evidence.")
    except DeadlineExceeded:
        ctx.error("deadline_exceeded", "The scan deadline was reached; unfinished coverage is reported as omitted.", True)
        S.on_deadline(ctx)
    try:
        with ctx.stage("publish"):
            S.publish_stage(ctx)
    except Exception:
        ctx.error("publish_failed", "Results could not be stored; this scan produced no usable observations.", True)
        final = ScanState.failed
    if final is None:
        final = _final_state(ctx)
    ctx.ledger and engine.repo.insert_ledger(ctx.ledger)
    ctx.persist()
    engine.repo.update_scan(scan["id"], state=final.value, finished_at=iso(now()))
    S.after_scan(ctx, final)
