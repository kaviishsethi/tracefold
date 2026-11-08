"""Takedown request drafting.

The request only contains public information and the company's own details: the public URL, the copied text as it
appears on that page (with anything secret-shaped masked), and who is asking. It never includes the private file's
name, path, surrounding text or any other private content.
"""
from __future__ import annotations

import re

from ..checks.rules import _ASSIGN, _PROVIDER_PATTERNS

MAX_EXCERPT = 600
SIGNATURE_PLACEHOLDER = "[Signed by the approver when this request is approved]"


def mask_secrets(text: str) -> str:
    """Mask credential-shaped values so approving a takedown never re-sends a live secret by email."""
    for _, rx in _PROVIDER_PATTERNS:
        text = rx.sub(lambda m: m.group(0).replace(m.group(1), _masked(m.group(1))), text)
    return _ASSIGN.sub(lambda m: m.group(0).replace(m.group(2), _masked(m.group(2))), text)


def _masked(v: str) -> str:
    return v[:4] + "•" * 8 if len(v) > 8 else "•" * 8


def excerpt(public_text: str) -> str:
    t = re.sub(r"\s+", " ", public_text).strip()
    if len(t) > MAX_EXCERPT:
        t = t[:MAX_EXCERPT].rsplit(" ", 1)[0] + " …"
    return mask_secrets(t)


def draft(host: str, url: str, quoted: str, retrieved_at: str | None) -> dict:
    """Subject and body, without the signature (added at approval time). Company details are filled at send time."""
    when = f" (retrieved {retrieved_at})" if retrieved_at else ""
    body = (
        f"Hello {host} team,\n\n"
        "I'm writing on behalf of {company}. The page below reproduces text from an internal, unpublished document "
        "that {company} owns. Its publication was not authorized.\n\n"
        f"Page: {url}\n"
        f"Copied text as it appears on the page{when}:\n\n"
        f"    \"{quoted}\"\n\n"
        "Please remove or disable access to this content.\n\n"
        "I have a good-faith belief that this use of the material is not authorized by {company}, its agents, or the "
        "law. The information in this notice is accurate, and under penalty of perjury, I am authorized to act on "
        "behalf of {company}.\n"
    )
    return {"subject": f"Removal request: unauthorized copy of internal content at {host}", "body": body}


def render(body: str, company: str, reply_to: str, approver: dict | None) -> str:
    """Fill company details and append the signature block."""
    # "Northwind Relay, Inc." at a sentence end must not become "Inc.."
    text = body.replace("{company}.", company if company.endswith(".") else company + ".").replace("{company}", company)
    if approver:
        title = f"{approver['title']}, " if approver.get("title") else ""
        sig = f"{approver['name']}\n{title}{company}\nReply to: {reply_to}\n"
    else:
        sig = f"{SIGNATURE_PLACEHOLDER}\n{company}\nReply to: {reply_to}\n"
    return text.rstrip() + "\n\n" + sig
