"""Approved public company identity and the deterministic, versioned query builder.

A company profile is configuration, approved by an operator-scoped client. It is the only input to the query
builder besides fixed templates, provider choice and a public-site scope. Nothing here reads uploaded
documents, filenames, embeddings, hashes or model output; switching the uploaded document cannot change a
plan's outbound queries. Validation is defense in depth: it cannot prove that an arbitrary name is public.
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata

from ..errors import ApiError
from .presets import MAX_RESULTS_PER_SEARCH, MAX_SEARCHES, PROVIDERS, QUERY_TEMPLATE_VERSION  # noqa: F401 (re-export)

PRIVACY_NOTICE_VERSION = "company_discovery_v1"
PRIVACY_NOTICE = ("Search providers see the public company identity and approved queries. They do not receive uploaded "
                  "document contents. Public names and search intent still leave this environment; do not enter secret "
                  "project names or private context here.")
MAX_ALIASES = 2

_NAME_OK = re.compile(r"^[\w &.,'()+!?-]+$", re.UNICODE)
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_KEYLIKE = re.compile(r"(sk-|ghp_|gho_|github_pat_|xox[abp]-|AKIA|tvly-|tf_)[A-Za-z0-9_-]{6,}|[A-Za-z0-9+/_-]{24,}")
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_BAD_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home", ".corp", ".intranet", ".test", ".invalid", ".example")


def clean_name(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ApiError(422, "invalid_profile", f"{field} must be text.")
    if any(unicodedata.category(c).startswith("C") for c in value):
        raise ApiError(422, "invalid_profile", f"{field} must not contain control characters.")
    v = " ".join(unicodedata.normalize("NFC", value).split())
    if not 2 <= len(v) <= 80:
        raise ApiError(422, "invalid_profile", f"{field} must be 2-80 characters.")
    if not _NAME_OK.match(v):
        raise ApiError(422, "invalid_profile",
                       f"{field} may only contain letters, digits, spaces and . , ' ( ) + ! ? & - (no quotes or search operators).")
    if any(tok.startswith("-") for tok in v.split()) or v.split()[0].upper() in ("OR", "AND", "NOT"):
        raise ApiError(422, "invalid_profile", f"{field} must not start a word with '-' or begin with a search operator.")
    if _EMAIL.search(v) or _KEYLIKE.search(v):
        raise ApiError(422, "invalid_profile", f"{field} looks like an email address or credential, not a public name.")
    return v


def clean_domain(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 253:
        raise ApiError(422, "invalid_profile", "official_domain must be a hostname.")
    v = value.strip().lower().rstrip(".")
    if v.startswith("www."):
        v = v[4:]
    try:
        ipaddress.ip_address(v.strip("[]"))
        raise ApiError(422, "invalid_profile", "official_domain must be a hostname, not an IP address.")
    except ValueError:
        pass
    labels = v.split(".")
    if len(labels) < 2 or not all(_LABEL.match(x) for x in labels) or labels[-1].isdigit():
        raise ApiError(422, "invalid_profile", "official_domain must be a bare public hostname (no scheme, port, path or query).")
    if v == "localhost" or v.endswith(_BAD_SUFFIXES):
        raise ApiError(422, "invalid_profile", "official_domain must be a public hostname.")
    return v


def validate_profile(display_name: str, official_domain: str | None, public_aliases: list[str] | None) -> dict:
    aliases = public_aliases or []
    if len(aliases) > MAX_ALIASES:
        raise ApiError(422, "invalid_profile", f"At most {MAX_ALIASES} public aliases are allowed.")
    name = clean_name(display_name, "display_name")
    cleaned = []
    for i, a in enumerate(aliases):
        a = clean_name(a, f"public_aliases[{i}]")
        if a.lower() != name.lower() and a.lower() not in (x.lower() for x in cleaned):
            cleaned.append(a)
    return {"display_name": name, "official_domain": clean_domain(official_domain), "public_aliases": cleaned}
