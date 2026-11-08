"""Revoke a leaked GitHub token through GitHub's public credential revocation API.

``POST https://api.github.com/credentials/revoke`` takes the leaked token itself and needs no account or setup:
GitHub revokes it and notifies the owner. Revocation can't be undone, so it runs only after a person approves.

The token is never stored. Drafting keeps it in engine memory keyed by its fingerprint; the saved action holds only
a masked form and the fingerprint. After an engine restart the token is gone and the file has to be scanned again.
"""
from __future__ import annotations

import hashlib
import re

from ..gateway.gateway import Gateway, GatewayDenied, Policy, mask_secret

HOST = "api.github.com"
TOKEN = re.compile(r"^(?:ghp|gho|ghu|ghr)_[A-Za-z0-9]{36,255}$|^github_pat_[A-Za-z0-9_]{22,255}$")
POLICY = Policy(category="provider_api", purpose="github_token_revoke", allowed_hosts=frozenset({HOST}),
                max_request_bytes=4096, max_response_bytes=16 * 1024, timeout=15.0, max_redirects=0)


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def masked(token: str) -> str:
    return mask_secret(token)


class GithubActionError(Exception):
    """A failure with a stable code and a message that never contains the token."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def revoke(gateway: Gateway, token: str) -> dict:
    try:
        r = gateway.request("POST", f"https://{HOST}/credentials/revoke", POLICY, json_body={"credentials": [token]},
                            headers={"accept": "application/vnd.github+json", "x-github-api-version": "2022-11-28"},
                            summary={"endpoint": "/credentials/revoke", "credentials": 1})
    except GatewayDenied as ex:
        raise GithubActionError("github_unreachable", f"Couldn't reach GitHub ({ex.reason}).")
    if r.status == 202:
        return {"revoked": True}
    if r.status == 422:
        raise GithubActionError("github_rejected", "GitHub didn't accept this token. It may already be revoked or not be a real token.")
    if r.status in (403, 429):
        raise GithubActionError("github_rate_limited", "GitHub's revoke limit was reached. Try again in an hour.")
    raise GithubActionError("github_error", f"GitHub returned HTTP {r.status}.")
