"""In-flight proposed observations, before validation and publication."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..inputs.registry import CapturedFile


@dataclass
class Proposed:
    kind: str                      # public_exposure | local_risk
    check_id: str                  # public_match | local_risk
    check_version: str
    rule_id: str | None
    origin: str                    # matcher | rule | model
    file: CapturedFile
    anchor: str                    # normalized evidence anchor used for conservative correlation
    title: str
    evidence: list[dict[str, Any]]  # evidence payloads (validated before publication)
    claim: str | None = None
    conditions: str | None = None
    missing_context: str | None = None
    uncertainty: str | None = None
    suggested_fix: str | None = None
    verification_step: str | None = None
    severity: str | None = None
    severity_rationale: str | None = None
    risk_review: str = "not_requested"
    counterevidence: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    secret_values: list[str] = field(default_factory=list)   # never persisted; used for output scrubbing
    source_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
