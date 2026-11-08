"""Untrusted candidate URLs: conservative canonicalization, stable source IDs and pre-fetch policy.

Canonicalization only normalizes scheme/host case, default ports and fragments. Paths and query strings are
kept as-is so different files or versions are never collapsed into one source.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit

from ..util import sha256

_BAD_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home", ".corp", ".intranet", ".arpa", ".test", ".invalid")
_HEX = set("0123456789abcdef")


def _numeric_host(host: str) -> bool:
    """Shorthand IPv4 forms that ipaddress rejects but resolvers accept: 127.1, 2130706433, 0x7f.0.0.1."""
    return all(l.isdigit() or (l.startswith("0x") and len(l) > 2 and set(l[2:]) <= _HEX) for l in host.split("."))
MAX_URL_LEN = 2048


def check_url(url: object) -> str | None:
    """Return a refusal reason, or None when the URL may be handed to a fetcher. DNS and redirect targets are
    checked again at connection time by the gateway for direct fetches."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LEN:
        return "invalid_url"
    if any(ord(c) < 0x21 or ord(c) == 0x7f for c in url):
        return "invalid_url"
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        return "invalid_url"
    if p.scheme.lower() not in ("http", "https"):
        return "scheme_not_allowed"
    if p.username or p.password or "@" in p.netloc:
        return "credentials_in_url"
    host = (p.hostname or "").lower().rstrip(".")
    if not host:
        return "invalid_url"
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None or _numeric_host(host):
        return "ip_literal_not_allowed"
    if host == "localhost" or host.endswith(_BAD_SUFFIXES) or "." not in host:
        return "private_destination"
    if port not in (None, 80, 443):
        return "port_not_allowed"
    return None


def canonicalize(url: str) -> str:
    p = urlsplit(url)
    scheme = p.scheme.lower()
    host = (p.hostname or "").lower().rstrip(".")
    port = p.port
    netloc = host if port in (None, 80 if scheme == "http" else 443) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, p.path or "/", p.query, ""))


def source_id_for(workspace_id: str, canonical_url: str) -> str:
    """Stable across runs and independent of provider rank."""
    return "d_" + sha256(f"discovered\n{workspace_id}\n{canonical_url}")[:20]
