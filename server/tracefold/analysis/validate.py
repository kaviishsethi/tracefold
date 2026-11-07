"""Structural evidence validation before publication.

Every candidate must cite an in-scope captured file whose hash matches, with locations inside the parsed
text. Public matches are re-confirmed by comparing normalized tokens on both sides. Model-originated text
is scrubbed for echoed secrets. Structural validity does not establish semantic correctness.
"""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from ..checks import matcher

if TYPE_CHECKING:
    from ..jobs.pipeline import ScanContext


def _valid_location(doc, loc: dict) -> bool:
    try:
        expected = doc.location(loc["start"], loc["end"])
    except (ValueError, KeyError, TypeError):
        return False
    return all(expected.get(k) == loc.get(k) for k in ("file_id", "line_start", "line_end", "paragraph_id"))


def validate_candidates(ctx: "ScanContext") -> tuple[list, dict[str, int]]:
    docs = {d.file.file_id: d for d in ctx.docs}
    file_secrets: dict[str, set[str]] = {}
    for p in ctx.candidates:
        file_secrets.setdefault(p.file.file_id, set()).update(v for v in p.secret_values if v)
    kept, rejected = [], Counter()
    for p in ctx.candidates:
        doc = docs.get(p.file.file_id)
        if doc is None or p.file.status != "captured" or not p.evidence:
            rejected["file_not_in_scope"] += 1
            continue
        ok = True
        for ev in p.evidence:
            if ev.get("file_sha256") != doc.file.sha256 or not _valid_location(doc, ev.get("location", {})):
                ok = False
                rejected["invalid_location"] += 1
                break
            if ev["kind"] == "public_match":
                pub = ev.get("public") or {}
                text = ctx.public_texts.get(pub.get("source_id"))
                if text is None or not (0 <= pub.get("start", -1) < pub.get("end", -1) <= len(text)):
                    ok = False
                    rejected["invalid_public_span"] += 1
                    break
                pol = ev.get("normalization", "text_v1")
                lt = [t.norm for t in matcher.tokenize(doc.text[ev["location"]["start"]:ev["location"]["end"]], pol)]
                pt = [t.norm for t in matcher.tokenize(text[pub["start"]:pub["end"]], pol)]
                if lt != pt or len(lt) != ev.get("matched_tokens"):
                    ok = False
                    rejected["public_span_mismatch"] += 1
                    break
        if not ok:
            continue
        if p.origin == "model" or p.risk_review not in ("not_requested", "unavailable"):
            from .privacy import scrub_candidate
            p.secret_values = sorted(set(p.secret_values) | file_secrets.get(p.file.file_id, set()))
            if not scrub_candidate(p, doc):
                rejected["privacy_scrub_failed"] += 1
                continue
        kept.append(p)
    return kept, dict(rejected)
