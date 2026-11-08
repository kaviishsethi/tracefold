"""Deterministic local risk rules. A rule hit is a lead with source evidence, not a confirmed exposure.

Python is analyzed with ``ast.parse`` only (never executed). Other code languages receive the
language-independent secret-literal rule and are reported as unsupported for the logging rule.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from ..parsing.document import ParsedDoc

RULES_VERSION = "rules_v1"


@dataclass
class RuleInfo:
    rule_id: str
    version: str
    applies_to: str
    title: str


RULES: dict[str, RuleInfo] = {
    "py_sensitive_logging": RuleInfo("py_sensitive_logging", "1", "python", "Potential sensitive value written to logs"),
    "secret_literal": RuleInfo("secret_literal", "1", "text, code, docx", "Apparent embedded secret"),
    "gitleaks_secret": RuleInfo("gitleaks_secret", "1", "text, code, docx", "Apparent embedded secret (Gitleaks rule)"),
    "doc_confidential_marker": RuleInfo("doc_confidential_marker", "1", "text, docx", "Document marked confidential"),
    "doc_personal_identifier": RuleInfo("doc_personal_identifier", "1", "text, docx", "Apparent personal identifier"),
    "industry_identifier": RuleInfo("industry_identifier", "1", "text, code, docx", "Regulated data for your industry"),
}

# Industry packs: extra checks switched on by the company's industry (Settings). Technology uses the base checks.
INDUSTRIES = {
    "financial": "Financial services",
    "healthcare": "Healthcare",
    "government": "Government and public sector",
    "retail": "Retail and e-commerce",
    "technology": "Technology",
}
INDUSTRY_PACKS: dict[str, list[str]] = {
    "financial": ["card", "iban", "routing"],
    "healthcare": ["mrn", "npi", "dob"],
    "government": ["cui", "passport"],
    "retail": ["card"],
    "technology": [],
}


@dataclass
class Hit:
    rule_id: str
    start: int
    end: int
    anchor: str
    title: str
    claim: str
    conditions: str
    missing_context: str
    suggested_fix: str
    verification_step: str
    severity: str
    severity_rationale: str
    uncertainty: str
    mask_spans: list[list[int]] = field(default_factory=list)
    secret_values: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


# ---------------- identifier sensitivity ----------------
_SENSITIVE_PARTS = {"password", "passwd", "pwd", "passphrase", "secret", "token", "apikey", "ssn", "cvv", "credential",
                    "credentials", "cookie", "privatekey", "authorization", "bearer"}
_SENSITIVE_BIGRAMS = {("api", "key"), ("private", "key"), ("card", "number"), ("card", "num"), ("session", "id"),
                      ("access", "key"), ("auth", "header"), ("social", "security"), ("refresh", "token"), ("client", "secret")}
_SAFE_PARTS = {"count", "len", "length", "type", "hash", "hashed", "digest", "masked", "redacted", "expiry", "expires",
               "expiration", "url", "endpoint", "policy", "field", "fields", "label", "prompt", "valid", "is", "has", "min", "max"}
_SAFE_WRAPPERS = {"mask", "redact", "hash", "sanitize", "scrub", "obfuscate", "len", "bool", "type", "hashlib", "sha256",
                  "censor", "truncate_secret", "mask_secret", "redact_secret"}


def ident_parts(name: str) -> list[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return [p for p in re.split(r"[^A-Za-z0-9]+", s.lower()) if p]


def is_sensitive_ident(name: str) -> bool:
    parts = ident_parts(name)
    if not parts or any(p in _SAFE_PARTS for p in parts):
        return False
    if any(p in _SENSITIVE_PARTS for p in parts):
        return True
    return any((a, b) in _SENSITIVE_BIGRAMS for a, b in zip(parts, parts[1:]))


def _wrapper_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_safe_wrapper(func: ast.expr) -> bool:
    name = _wrapper_name(func)
    if not name:
        return False
    parts = set(ident_parts(name))
    return name.lower() in _SAFE_WRAPPERS or bool(parts & {"mask", "redact", "hash", "sanitize", "scrub", "obfuscate"})


def _sensitive_refs(node: ast.AST) -> list[tuple[ast.AST, str]]:
    """Sensitive references inside an expression, skipping anything wrapped by a masking/hash call."""
    out: list[tuple[ast.AST, str]] = []

    def visit(n: ast.AST) -> None:
        if isinstance(n, ast.Call):
            if _is_safe_wrapper(n.func):
                return
            if isinstance(n.func, ast.Attribute):
                visit(n.func)  # e.g. user.get_password() or password.strip()
            for a in n.args:
                visit(a)
            for kw in n.keywords:
                visit(kw.value)
            return
        if isinstance(n, ast.Name):
            if is_sensitive_ident(n.id):
                out.append((n, n.id))
            return
        if isinstance(n, ast.Attribute):
            if is_sensitive_ident(n.attr):
                out.append((n, n.attr))
                return
            visit(n.value)
            return
        if isinstance(n, ast.Subscript):
            sl = n.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str) and is_sensitive_ident(sl.value):
                out.append((n, sl.value))
                return
            visit(n.value)
            visit(sl)
            return
        if isinstance(n, ast.Constant):
            return
        for child in ast.iter_child_nodes(n):
            visit(child)

    visit(node)
    return out


_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "critical", "exception", "log", "fatal"}
_LOGGER_NAME = re.compile(r"^_?(log|logger|logging|LOG|LOGGER|Logger|audit_log|app_logger|root_logger)$")


def _is_log_call(call: ast.Call) -> bool:
    f = call.func
    if isinstance(f, ast.Name) and f.id == "print":
        return True
    if isinstance(f, ast.Attribute) and f.attr in _LOG_METHODS:
        v = f.value
        if isinstance(v, ast.Name) and _LOGGER_NAME.match(v.id):
            return True
        if isinstance(v, ast.Attribute) and (v.attr in ("logger", "log", "_logger", "_log")):
            return True
        if isinstance(v, ast.Call) and _wrapper_name(v.func) == "getLogger":
            return True
    return False


def _offset(doc: ParsedDoc, line: int, col_bytes: int) -> int:
    ls, le = doc.line_span(line)
    line_text = doc.text[ls:le]
    return ls + len(line_text.encode("utf-8")[:col_bytes].decode("utf-8", "ignore"))


def _norm_anchor(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def python_logging(doc: ParsedDoc) -> tuple[list[Hit], str | None]:
    try:
        tree = ast.parse(doc.text, filename="<captured>", mode="exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return [], "python_syntax_error"
    hits: list[Hit] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_log_call(node)):
            continue
        refs: list[tuple[ast.AST, str]] = []
        for a in node.args:
            refs += _sensitive_refs(a)
        for kw in node.keywords:
            if kw.arg not in ("exc_info", "stack_info", "stacklevel", "extra"):
                refs += _sensitive_refs(kw.value)
            elif kw.arg == "extra":
                refs += _sensitive_refs(kw.value)
        if not refs:
            continue
        start = _offset(doc, node.lineno, node.col_offset)
        end = _offset(doc, node.end_lineno or node.lineno, node.end_col_offset or 0)
        if end <= start:
            continue
        names = sorted({n for _, n in refs})
        sink = "print()" if isinstance(node.func, ast.Name) else f"logger.{node.func.attr}()"  # type: ignore[union-attr]
        hits.append(Hit(
            rule_id="py_sensitive_logging", start=start, end=end,
            anchor="|".join(names) + "|" + _norm_anchor(doc.text[start:end]),
            title=RULES["py_sensitive_logging"].title,
            claim=f"A value named {', '.join(repr(n) for n in names)} is passed to {sink} without an apparent masking step.",
            conditions="Risk arises if this code path runs where log output is retained, shipped to a log service, or readable "
                       "by people who should not see this value.",
            missing_context="Log level configuration, log destinations and any downstream filtering are not visible in this file.",
            suggested_fix=f"Remove {', '.join(names)} from the log call, or log a masked/derived value instead "
                          "(for example a fixed placeholder or a short non-reversible fingerprint).",
            verification_step="Re-run the recheck for this finding, then exercise the code path and confirm the emitted log line "
                              "contains no sensitive value.",
            severity="medium",
            severity_rationale="Sensitive values in logs commonly outlive the request and reach wider audiences than the data itself.",
            uncertainty="Rule-based pattern match on identifier names; the value may already be masked elsewhere or be non-sensitive.",
            meta={"names": names, "line": node.lineno},
        ))
    return hits, None


# ---------------- secret literals ----------------
_PROVIDER_PATTERNS = [
    ("aws_access_key_id", re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b")),
    ("github_token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,255})\b")),
    ("github_token", re.compile(r"\b(github_pat_[A-Za-z0-9_]{22,255})\b")),
    ("slack_token", re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b")),
    ("stripe_live_key", re.compile(r"\b((?:sk|rk)_live_[0-9A-Za-z]{24,})\b")),
    ("private_key_block", re.compile(r"(-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----)")),
]
_ASSIGN = re.compile(
    r"""(?ix)\b([A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|api[_-]?key|token|access[_-]?key|auth[_-]?key|private[_-]?key)[A-Za-z0-9_.-]*)
        \s*(?::|=|:=|=>)\s*["']([^"'\s]{8,200})["']""")
_PLACEHOLDER = re.compile(r"(?i)(changeme|change_me|example|placeholder|dummy|your[_-]|xxx|<|>|\$\{|\{\{|redacted|\*\*\*|not[_-]?a[_-]?secret|sample|todo|replace)")


def _mask_value(v: str) -> str:
    return (v[:4] if len(v) > 12 else "") + "…" + f"({len(v)} chars)"


def secret_literals(doc: ParsedDoc) -> list[Hit]:
    hits: list[Hit] = []
    seen: set[tuple[int, int]] = set()

    def add(kind: str, vstart: int, vend: int, label: str) -> None:
        value = doc.text[vstart:vend]
        if (vstart, vend) in seen or _PLACEHOLDER.search(value):
            return
        seen.add((vstart, vend))
        ls = doc.text.rfind("\n", 0, vstart) + 1
        le = doc.text.find("\n", vend)
        le = len(doc.text) if le < 0 else le
        line_masked = doc.text[ls:vstart] + "<value>" + doc.text[vend:le]
        hits.append(Hit(
            rule_id="secret_literal", start=vstart, end=vend,
            anchor=f"{kind}|{label}|" + _norm_anchor(line_masked),
            title=RULES["secret_literal"].title,
            claim=f"A value matching the {kind.replace('_', ' ')} pattern{f' (assigned to {label!r})' if label else ''} is embedded "
                  f"in this file [{_mask_value(value)}].",
            conditions="Risk arises if this file is shared, committed to a repository others can read, or published, and the value "
                       "is a real, active credential.",
            missing_context="Whether the value is real, active, or scoped is unknown; Tracefold never tests credentials.",
            suggested_fix="Move the value to a secret manager or environment configuration excluded from source control; if it "
                          "may have been exposed, have its owner rotate it.",
            verification_step="Re-run the recheck for this finding and confirm the literal no longer appears; separately confirm "
                              "rotation with the credential's owner if exposure is possible.",
            severity="high",
            severity_rationale="An embedded live credential can grant direct access to the system it belongs to.",
            uncertainty="Format-based detection; the value may be a test value or already revoked.",
            mask_spans=[[vstart, vend]], secret_values=[value], meta={"pattern": kind},
        ))

    for kind, rx in _PROVIDER_PATTERNS:
        for m in rx.finditer(doc.text):
            add(kind, m.start(1), m.end(1), "")
    for m in _ASSIGN.finditer(doc.text):
        add("assigned_secret", m.start(2), m.end(2), m.group(1)[-60:])
    return hits


def gitleaks_hits(doc: ParsedDoc, leaks: list, existing: list[Hit]) -> tuple[list[Hit], int]:
    """Turn sandboxed Gitleaks leads into hits. Overlaps with a built-in ``secret_literal`` hit are merged into
    that hit (its masking widens to cover the Gitleaks span) instead of producing a duplicate finding.
    Returns (new hits, number of leads that could not be located in our own text)."""
    from .gitleaks import locate

    builtin = [h for h in existing if h.rule_id == "secret_literal"]
    taken: set[tuple[int, int]] = set()
    out: list[Hit] = []
    unlocated = 0
    for leak in leaks:
        sp = locate(doc.text, doc.line_starts, leak, taken)
        if sp is None:
            unlocated += 1
            continue
        vstart, vend = sp
        value = doc.text[vstart:vend]
        if _PLACEHOLDER.search(value):
            continue
        taken.add(sp)
        merged = False
        for h in builtin + out:
            if h.start < vend and vstart < h.end:
                if value not in h.secret_values:
                    h.secret_values.append(value)
                if [vstart, vend] not in h.mask_spans:
                    h.mask_spans.append([vstart, vend])
                h.meta.setdefault("gitleaks_rules", [])
                if leak.rule not in h.meta["gitleaks_rules"]:
                    h.meta["gitleaks_rules"].append(leak.rule)
                merged = True
                break
        if merged:
            continue
        ls = doc.text.rfind("\n", 0, vstart) + 1
        le = doc.text.find("\n", vend)
        le = len(doc.text) if le < 0 else le
        line_masked = doc.text[ls:vstart] + "<value>" + doc.text[vend:le]
        out.append(Hit(
            rule_id="gitleaks_secret", start=vstart, end=vend,
            anchor=f"gitleaks|{leak.rule}|" + _norm_anchor(line_masked),
            title=RULES["gitleaks_secret"].title,
            claim=f"A value matching the Gitleaks rule {leak.rule!r} is embedded in this file [{_mask_value(value)}].",
            conditions="Risk arises if this file is shared, committed to a repository others can read, or published, and the value "
                       "is a real, active credential.",
            missing_context="Whether the value is real, active, or scoped is unknown; neither Tracefold nor its sandboxed Gitleaks "
                            "run tests credentials.",
            suggested_fix="Move the value to a secret manager or environment configuration excluded from source control; if it "
                          "may have been exposed, have its owner rotate it.",
            verification_step="Re-run the recheck for this finding and confirm the value no longer appears; separately confirm "
                              "rotation with the credential's owner if exposure is possible.",
            severity="high",
            severity_rationale="An embedded live credential can grant direct access to the system it belongs to.",
            uncertainty="Format- and entropy-based detection by Gitleaks; the value may be a test value or already revoked.",
            mask_spans=[[vstart, vend]], secret_values=[value],
            meta={"pattern": leak.rule, "detector": "gitleaks", **({"entropy": leak.entropy} if leak.entropy is not None else {})},
        ))
    return out, unlocated


def check_version(rule_id: str, gitleaks_version: str | None = None) -> str:
    base = f"{RULES_VERSION}/{rule_id}@{RULES[rule_id].version}"
    return f"{base}+{gitleaks_version}" if rule_id == "gitleaks_secret" else base


# ---------------- document checks ----------------
_CONFIDENTIAL = re.compile(r"(?i)\b(strictly confidential|confidential|internal use only|internal only|do not distribute|"
                           r"not for (?:external )?distribution|proprietary and confidential)\b")
_SSN = re.compile(r"\b(?!000|666|9\d\d)(\d{3})-(?!00)(\d{2})-(?!0000)(\d{4})\b")


def document_checks(doc: ParsedDoc) -> list[Hit]:
    hits: list[Hit] = []
    m = _CONFIDENTIAL.search(doc.text)
    if m:
        marker = m.group(1).lower()
        hits.append(Hit(
            rule_id="doc_confidential_marker", start=m.start(1), end=m.end(1), anchor=f"marker|{marker}",
            title=RULES["doc_confidential_marker"].title,
            claim=f"The document carries the marker {m.group(1)!r}, indicating restricted distribution.",
            conditions="Risk arises if the document is shared beyond its intended audience or published; check where copies exist.",
            missing_context="The intended audience and any sharing approvals are not known from the file.",
            suggested_fix="Confirm the intended audience before sharing; remove or redact restricted sections for wider audiences.",
            verification_step="Review the sharing destination's access list; run a public match against monitored sources.",
            severity="low",
            severity_rationale="A marker signals intent, not harm; impact depends on content and where it is shared.",
            uncertainty="Keyword detection; the marker may be boilerplate or outdated.",
        ))
    for m in _SSN.finditer(doc.text):
        hits.append(Hit(
            rule_id="doc_personal_identifier", start=m.start(), end=m.end(),
            anchor="ssn|" + _norm_anchor(doc.text[max(0, m.start() - 40):m.start()]),
            title=RULES["doc_personal_identifier"].title,
            claim="A value formatted like a US Social Security number appears in this document [masked].",
            conditions="Risk arises if the document is shared with anyone not authorized to see personal identifiers.",
            missing_context="Whether the value is a real identifier, and the document's audience, are unknown.",
            suggested_fix="Redact the identifier before sharing, or restrict the document to authorized readers.",
            verification_step="Re-run the recheck for this finding after redaction.",
            severity="high",
            severity_rationale="Government identifiers enable identity fraud and carry regulatory obligations.",
            uncertainty="Format-based detection; numbers with this shape are not always identifiers.",
            mask_spans=[[m.start(), m.end()]], secret_values=[m.group(0)],
        ))
    return hits


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _iban_ok(v: str) -> bool:
    v = v.replace(" ", "").upper()
    if not 15 <= len(v) <= 34:
        return False
    n = "".join(str(int(ch, 36)) for ch in v[4:] + v[:4])
    return int(n) % 97 == 1


def _aba_ok(v: str) -> bool:
    d = [int(c) for c in v]
    return len(d) == 9 and (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10 == 0


_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
_ROUTING = re.compile(r"(?i)\b(?:routing|aba|rtn)(?: number| no\.?| #)?\s*[:#=]?\s*(\d{9})\b")
_MRN = re.compile(r"(?i)\b(?:mrn|medical record(?: number| no\.?| #)?)\s*[:#=]?\s*([A-Z0-9-]{5,15})\b")
_NPI = re.compile(r"(?i)\bnpi(?: number| no\.?| #)?\s*[:#=]?\s*(\d{10})\b")
_DOB = re.compile(r"(?i)\b(?:dob|date of birth|birth ?date)\s*[:#=]?\s*(\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4})\b")
_CUI = re.compile(r"\b(CONTROLLED UNCLASSIFIED INFORMATION|CUI//[A-Z-]+|FOR OFFICIAL USE ONLY|FOUO|LAW ENFORCEMENT SENSITIVE)\b")
_PASSPORT = re.compile(r"(?i)\bpassport(?: number| no\.?| #)?\s*[:#=]?\s*([A-Z0-9]{6,9})\b")

_PACK_INFO = {  # key: (title, claim, severity, mask the value?)
    "card": ("Apparent payment card number", "A number that passes the card checksum appears here [masked].", "high", True),
    "iban": ("Apparent bank account (IBAN)", "A value that passes the IBAN checksum appears here [masked].", "high", True),
    "routing": ("Apparent bank routing number", "A labeled US routing number that passes the ABA checksum appears here [masked].", "medium", True),
    "mrn": ("Apparent medical record number", "A labeled medical record number appears here [masked].", "high", True),
    "npi": ("Apparent provider NPI", "A labeled National Provider Identifier that passes its checksum appears here [masked].", "medium", True),
    "dob": ("Apparent date of birth", "A labeled date of birth appears here [masked].", "medium", True),
    "cui": ("Government handling marking", "The document carries a government handling marking.", "medium", False),
    "passport": ("Apparent passport number", "A labeled passport number appears here [masked].", "high", True),
}


def industry_checks(doc: ParsedDoc, industry: str | None) -> list[Hit]:
    hits: list[Hit] = []
    seen: set[tuple[int, int]] = set()

    def add(key: str, start: int, end: int, value: str):
        if (start, end) in seen:
            return
        seen.add((start, end))
        title, claim, severity, mask = _PACK_INFO[key]
        hits.append(Hit(
            rule_id="industry_identifier", start=start, end=end,
            anchor=f"{key}|" + _norm_anchor(doc.text[max(0, start - 40):start]),
            title=title, claim=claim,
            conditions="Risk arises if this file is shared beyond people allowed to see regulated data.",
            missing_context="Whether the value is real, and who is allowed to see this file, are unknown.",
            suggested_fix="Remove or redact the value, or keep the file only where regulated data is allowed.",
            verification_step="Re-run the recheck for this finding after redaction.",
            severity=severity,
            severity_rationale=f"Checked because the company's industry is {INDUSTRIES.get(industry or '', industry)}.",
            uncertainty="Pattern and checksum detection; test data and look-alike numbers can match.",
            mask_spans=[[start, end]] if mask else [], secret_values=[value] if mask else [],
            meta={"pack": key, "industry": industry},
        ))

    for key in INDUSTRY_PACKS.get(industry or "", []):
        if key == "card":
            for m in _CARD.finditer(doc.text):
                digits = re.sub(r"\D", "", m.group())
                if 13 <= len(digits) <= 19 and digits[0] in "3456" and _luhn(digits) and len(set(digits)) > 1:
                    add(key, m.start(), m.end(), m.group())
        elif key == "iban":
            for m in _IBAN.finditer(doc.text):
                if _iban_ok(m.group()):
                    add(key, m.start(), m.end(), m.group())
        elif key == "routing":
            for m in _ROUTING.finditer(doc.text):
                if _aba_ok(m.group(1)):
                    add(key, m.start(1), m.end(1), m.group(1))
        elif key == "npi":
            for m in _NPI.finditer(doc.text):
                if _luhn("80840" + m.group(1)):
                    add(key, m.start(1), m.end(1), m.group(1))
        else:
            rx = {"mrn": _MRN, "dob": _DOB, "cui": _CUI, "passport": _PASSPORT}[key]
            for m in rx.finditer(doc.text):
                add(key, m.start(1), m.end(1), m.group(1))
    return hits


def run_rules(doc: ParsedDoc, industry: str | None = None) -> tuple[list[Hit], dict[str, str]]:
    """Returns hits and per-rule coverage notes for this document ({rule_id: reason}) where a rule did not apply fully."""
    notes: dict[str, str] = {}
    hits = secret_literals(doc)
    if doc.kind == "code":
        if doc.language == "python":
            py, err = python_logging(doc)
            hits += py
            if err:
                notes["py_sensitive_logging"] = err
        else:
            notes["py_sensitive_logging"] = "unsupported_language"
    else:
        hits += document_checks(doc)
    hits += industry_checks(doc, industry)
    return hits, notes
