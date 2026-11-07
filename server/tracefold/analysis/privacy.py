"""Sanitize model-generated text before it is persisted or returned.

Removes any detected secret value and replaces long verbatim echoes of the private input (≥ ECHO_TOKENS
contiguous normalized tokens) with a placeholder. This narrows what model text can carry; it is not a
universal data-loss-prevention guarantee.
"""
from __future__ import annotations

from ..checks import matcher

ECHO_TOKENS = 10
FIELDS = ("claim", "conditions", "missing_context", "suggested_fix", "severity_rationale", "counterevidence")
PLACEHOLDER = "[quoted source omitted]"


def scrub_text(text: str | None, doc_text: str, secrets: list[str]) -> str | None:
    if not text:
        return text
    for v in secrets:
        if v and v in text:
            text = text.replace(v, "<masked-secret>")
    cfg = matcher.MatcherConfig(shingle=ECHO_TOKENS, min_tokens_text=ECHO_TOKENS, min_tokens_code=ECHO_TOKENS)
    res = matcher.find_matches(text, doc_text, "text_v1", cfg)
    for m in sorted(res.matches, key=lambda m: m.local_start, reverse=True):
        text = text[: m.local_start] + PLACEHOLDER + text[m.local_end:]
    return text


def scrub_candidate(p, doc) -> bool:
    """Scrub model-originated fields in place. Rule-template text is fixed and not scrubbed."""
    model_fields = FIELDS if p.origin == "model" else ("conditions", "missing_context", "suggested_fix",
                                                         "severity_rationale", "counterevidence")
    for f in model_fields:
        setattr(p, f, scrub_text(getattr(p, f), doc.text, p.secret_values))
    for f in model_fields:
        v = getattr(p, f)
        if v and any(s and s in v for s in p.secret_values):
            return False
    return True
