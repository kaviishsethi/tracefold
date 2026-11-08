"""Disable a leaked AWS access key through IAM, using the company's own remediation credentials.

Never uses the leaked key itself. The remediation principal needs only ``iam:GetAccessKeyLastUsed`` and
``iam:UpdateAccessKey``. The flow looks up the key's owning IAM user, then sets the key to Inactive. It never
deletes the key and never creates a replacement: re-enabling is one IAM call if the key turns out to be needed.

Requests are signed with AWS Signature Version 4 here (no SDK) so that they go through the engine gateway like
every other outbound call.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

from ..gateway.gateway import Gateway, GatewayDenied, Policy, mask_secret

IAM_HOST = "iam.amazonaws.com"
IAM_REGION = "us-east-1"  # IAM is a global service signed for us-east-1
IAM_VERSION = "2010-05-08"
NS = {"iam": "https://iam.amazonaws.com/doc/2010-05-08/"}
ACCESS_KEY_ID = re.compile(r"^AKIA[0-9A-Z]{16}$")  # long-term keys only; ASIA… session keys can't be disabled this way

POLICY = Policy(category="provider_api", purpose="aws_key_disable", allowed_hosts=frozenset({IAM_HOST}),
                max_request_bytes=4096, max_response_bytes=64 * 1024, timeout=15.0, max_redirects=0)

ENV_KEY_ID = "TRACEFOLD_AWS_REMEDIATION_ACCESS_KEY_ID"
ENV_SECRET = "TRACEFOLD_AWS_REMEDIATION_SECRET_ACCESS_KEY"
ENV_TOKEN = "TRACEFOLD_AWS_REMEDIATION_SESSION_TOKEN"


@dataclass(frozen=True)
class AwsCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: str | None = None

    def __repr__(self) -> str:
        return f"AwsCredentials(access_key_id={mask_secret(self.access_key_id)!r})"

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "AwsCredentials | None":
        kid, secret = env.get(ENV_KEY_ID), env.get(ENV_SECRET)
        if not kid or not secret:
            return None
        return cls(kid, secret, env.get(ENV_TOKEN) or None)


class AwsActionError(Exception):
    """A failure with a stable code and a message that never contains credentials."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _enc(s: str) -> str:
    return quote(s, safe="-_.~")


def canonical_query(params: dict[str, str]) -> str:
    return "&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(params.items()))


def sign_v4(method: str, host: str, path: str, query: str, headers: dict[str, str], body: bytes,
            creds: AwsCredentials, region: str, service: str, amz_date: str) -> str:
    """Return the Authorization header value. ``headers`` must include host and x-amz-date."""
    lower = {k.lower(): " ".join(v.strip().split()) for k, v in headers.items()}
    signed = ";".join(sorted(lower))
    canonical_headers = "".join(f"{k}:{lower[k]}\n" for k in sorted(lower))
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_request = "\n".join([method, path, query, canonical_headers, signed, payload_hash])
    date = amz_date[:8]
    scope = f"{date}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()])
    k = _hmac(("AWS4" + creds.secret_access_key).encode(), date)
    for part in (region, service, "aws4_request"):
        k = _hmac(k, part)
    signature = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"AWS4-HMAC-SHA256 Credential={creds.access_key_id}/{scope}, SignedHeaders={signed}, Signature={signature}"


class IamClient:
    def __init__(self, creds: AwsCredentials, gateway: Gateway, clock=lambda: datetime.now(timezone.utc)):
        self.creds, self.gw, self.clock = creds, gateway, clock

    def _call(self, action: str, params: dict[str, str], key_for_log: str) -> ET.Element:
        form = canonical_query({"Action": action, "Version": IAM_VERSION, **params}).encode()
        amz_date = self.clock().strftime("%Y%m%dT%H%M%SZ")
        headers = {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8", "Host": IAM_HOST, "X-Amz-Date": amz_date}
        if self.creds.session_token:
            headers["X-Amz-Security-Token"] = self.creds.session_token
        headers["Authorization"] = sign_v4("POST", IAM_HOST, "/", "", headers, form, self.creds, IAM_REGION, "iam", amz_date)
        try:
            r = self.gw.request("POST", f"https://{IAM_HOST}/", POLICY, headers=headers, content=form,
                                content_type=headers["Content-Type"],
                                summary={"api": f"iam:{action}", "access_key": mask_secret(key_for_log)})
        except GatewayDenied as ex:
            raise AwsActionError("aws_unreachable", f"Could not reach AWS IAM ({ex.reason}).") from None
        try:
            root = ET.fromstring(r.body)
        except ET.ParseError:
            raise AwsActionError("aws_bad_response", f"AWS IAM returned an unreadable response (HTTP {r.status}).") from None
        if r.status >= 400:
            code = root.findtext(".//{*}Error/{*}Code") or f"http_{r.status}"
            raise AwsActionError(_map_error(code), _error_message(code))
        return root

    def owner_of(self, access_key_id: str) -> str:
        root = self._call("GetAccessKeyLastUsed", {"AccessKeyId": access_key_id}, access_key_id)
        user = root.findtext(".//iam:GetAccessKeyLastUsedResult/iam:UserName", namespaces=NS)
        if not user:
            raise AwsActionError("aws_key_owner_unknown", "AWS did not report an IAM user for this key (it may be a root key).")
        return user

    def deactivate(self, access_key_id: str, user_name: str) -> None:
        self._call("UpdateAccessKey", {"AccessKeyId": access_key_id, "UserName": user_name, "Status": "Inactive"}, access_key_id)


def _map_error(code: str) -> str:
    return {
        "AccessDenied": "aws_access_denied",
        "NoSuchEntity": "aws_key_not_found",
        "InvalidClientTokenId": "aws_remediation_credentials_invalid",
        "SignatureDoesNotMatch": "aws_remediation_credentials_invalid",
        "Throttling": "aws_throttled",
    }.get(code, "aws_error")


def _error_message(code: str) -> str:
    return {
        "AccessDenied": "The remediation credentials can't manage this key. It may belong to a different AWS account, "
                        "or the remediation policy is missing iam:GetAccessKeyLastUsed / iam:UpdateAccessKey.",
        "NoSuchEntity": "AWS has no such access key in this account. It may already be deleted.",
        "InvalidClientTokenId": "The configured remediation credentials were rejected by AWS.",
        "SignatureDoesNotMatch": "The configured remediation credentials were rejected by AWS.",
        "Throttling": "AWS throttled the request. Approve again in a moment.",
    }.get(code, f"AWS IAM returned the error {code}.")


def disable_key(creds: AwsCredentials, gateway: Gateway, access_key_id: str, clock=None) -> dict:
    """Look up the owning user and set the key Inactive. Returns a result safe to store and show."""
    if not ACCESS_KEY_ID.match(access_key_id):
        raise AwsActionError("aws_key_not_supported", "Only long-term AWS access keys (AKIA…) can be disabled.")
    iam = IamClient(creds, gateway, **({"clock": clock} if clock else {}))
    user = iam.owner_of(access_key_id)
    iam.deactivate(access_key_id, user)
    return {"aws_status": "Inactive", "iam_user": user}
