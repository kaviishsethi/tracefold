"""Milestone 8: approval-gated remediation (takedown requests, disabling leaked AWS keys)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from tracefold.gateway.gateway import Gateway

from .conftest import PUBLIC, fx

WS = "/v1/workspaces/ws_a"
LEAKED = "AKIAQX7TFOLDDEMO2K4Z"
REMEDIATION_KEY = "AKIAREMEDIATIONK3Y9Z"
APPROVER = {"name": "Dana Ruiz", "email": "dana@northwind.example", "title": "General Counsel"}
IAM_NS = "https://iam.amazonaws.com/doc/2010-05-08/"


def public_scan(env, who="app"):
    inp = env.upload({"roadmap.md": fx("roadmap.md")}, who=who)
    return env.scan(inp["input_id"], checks=["public_match"], public_sources=PUBLIC, who=who)


def actions(env, who="app", **params):
    r = env.client.get(f"{WS}/actions", headers=env.h(who), params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def takedown(env, who="app"):
    return next(a for a in actions(env, who) if a["kind"] == "takedown_request")


def approve(env, a, who="app", attest=True, version=None):
    return env.client.post(f"{WS}/actions/{a['action_id']}/approve", headers=env.h(who), json={
        "approver": APPROVER, "attest_authorized": attest, "expected_version": a["version"] if version is None else version})


def setup_takedown(env, email=None, form_url=None):
    env.engine.set_remediation_profile("ws_a", "Northwind Relay, Inc.", "legal@northwind.example")
    env.engine.add_takedown_contact("ws_a", "forum.example", email=email, form_url=form_url)


def ledger(env):
    return env.engine.repo.all_ledger()


# ---------------- takedowns ----------------
def test_public_match_drafts_takedown_with_public_content_only(env):
    public_scan(env)
    a = takedown(env)
    assert a["status"] == "drafted" and a["target"]["host"] == "forum.example"
    assert a["target"]["url"] == "https://forum.example/t/123"
    assert "Harbor ingestion cluster" in a["target"]["excerpt"]
    assert "https://forum.example/t/123" in a["body"] and "Harbor ingestion cluster" in a["body"]
    for private in ("roadmap.md", "forty minutes", "41,000"):  # filename and private-only text never appear
        assert private not in a["body"] and private not in a["subject"]
    assert "[Signed by the approver" in a["body"]
    assert a["delivery"] == {"method": "none", "address": None, "form_url": None, "transport": None}


def test_approve_needs_profile_contact_attestation_and_capability(env):
    public_scan(env)
    a = takedown(env)
    r = approve(env, a)
    assert r.status_code == 409 and r.json()["error"]["code"] == "remediation_profile_missing"
    env.engine.set_remediation_profile("ws_a", "Northwind Relay, Inc.", "legal@northwind.example")
    r = approve(env, a)
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_takedown_contact"
    env.engine.add_takedown_contact("ws_a", "forum.example", email="abuse@forum.example")
    assert approve(env, a, attest=False).status_code == 422
    assert approve(env, a, who="reader").status_code == 403  # read-only client
    assert approve(env, a, version=a["version"] + 5).json()["error"]["code"] == "version_conflict"
    assert takedown(env)["status"] == "drafted"


def test_email_approval_sends_once_through_outbox(env):
    public_scan(env)
    setup_takedown(env, email="abuse@forum.example")
    a = takedown(env)
    assert a["delivery"]["method"] == "email" and a["delivery"]["transport"] == "outbox"
    r = approve(env, a)
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["status"] == "submitted" and done["result"]["sent_to"] == "abuse@forum.example"
    assert done["approver"]["name"] == "Dana Ruiz" and done["removal_observed"] is False
    eml = (env.engine.settings.data_dir / "outbox" / f"{a['action_id']}.eml").read_text()
    assert "To: abuse@forum.example" in eml and "Reply-To: legal@northwind.example" in eml
    assert "Dana Ruiz" in eml and "General Counsel, Northwind Relay, Inc." in eml and "roadmap.md" not in eml
    assert any(e["destination_category"] == "local_outbox" for e in ledger(env))
    again = approve(env, done)
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_state"


def test_minimal_disclosure_hides_letter_and_excerpt(env):
    public_scan(env)
    a = takedown(env, who="cloud")
    assert a["body"] is None and a["subject"] is None and "excerpt" not in a["target"]
    assert approve(env, a, who="cloud").status_code == 403  # no approve capability


def test_edit_and_reject(env):
    public_scan(env)
    a = takedown(env)
    r = env.client.patch(f"{WS}/actions/{a['action_id']}", headers=env.h(),
                         json={"subject": "Copyright removal request", "expected_version": a["version"]})
    assert r.status_code == 200 and r.json()["subject"] == "Copyright removal request"
    r = env.client.post(f"{WS}/actions/{a['action_id']}/reject", headers=env.h(),
                        json={"reason": "Publication was authorized", "expected_version": r.json()["version"]})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert approve(env, r.json()).json()["error"]["code"] == "invalid_state"


def test_form_host_then_removal_observed_after_fresh_scan(env):
    public_scan(env)
    setup_takedown(env, form_url="https://forum.example/legal/removal")
    a = takedown(env)
    r = approve(env, a).json()
    assert r["status"] == "awaiting_manual_submission" and r["result"]["form_url"] == "https://forum.example/legal/removal"
    assert not (env.engine.settings.data_dir / "outbox").exists()  # nothing was sent
    r = env.client.post(f"{WS}/actions/{a['action_id']}/mark-submitted", headers=env.h(),
                        json={"expected_version": r["version"], "note": "Filed via host form"})
    assert r.status_code == 200 and r.json()["status"] == "submitted" and r.json()["removal_observed"] is False
    # the page drops the passage: only a fresh successful scan marks the finding no longer observed
    env.engine.repo.put_manifest("ws_a", "sources_demo", [
        {"source_id": "forum", "url": "https://forum.example/t/123", "provider": "fixture", "mode": "seeded",
         "fixture_path": "public/vendor_blog.html"}])
    public_scan(env)
    assert takedown(env)["removal_observed"] is True


def test_resend_transport_logs_only_recipient_domain(env):
    public_scan(env)
    setup_takedown(env, email="abuse@forum.example")
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"id": "msg_123"})

    env.engine.remediation.gateway = Gateway(transport=httpx.MockTransport(handler), resolver=lambda h, p: ["93.184.216.34"])
    env.engine.remediation.env = {"TRACEFOLD_MAIL_TRANSPORT": "resend", "RESEND_API_KEY": "re_test_key",
                                  "TRACEFOLD_MAIL_FROM": "takedowns@northwind.example"}
    a = takedown(env)
    assert a["delivery"]["transport"] == "resend"
    done = approve(env, a).json()
    assert done["status"] == "submitted" and done["result"] == {"transport": "resend", "message_id": "msg_123",
                                                                 "sent_to": "abuse@forum.example"}
    (req,) = seen
    assert str(req.url) == "https://api.resend.com/emails" and req.headers["authorization"] == "Bearer re_test_key"
    sent = json.loads(req.content)
    assert sent["to"] == ["abuse@forum.example"] and "Dana Ruiz" in sent["text"]
    ev = next(e for e in ledger(env) if e["destination_category"] == "takedown_email")
    assert ev["payload_summary"]["recipient_domain"] == "forum.example"
    assert "Harbor" not in json.dumps(ev) and "re_test_key" not in json.dumps(ledger(env))


def test_unconfigured_resend_fails_and_can_be_retried(env):
    public_scan(env)
    setup_takedown(env, email="abuse@forum.example")
    env.engine.remediation.env = {"TRACEFOLD_MAIL_TRANSPORT": "resend"}
    failed = approve(env, takedown(env)).json()
    assert failed["status"] == "failed" and failed["result"]["error"]["code"] == "mail_not_configured"
    env.engine.remediation.env = {}  # back to the outbox
    assert approve(env, failed).json()["status"] == "submitted"


def test_drafting_is_idempotent_across_rescans(env):
    public_scan(env)
    public_scan(env)
    assert len([a for a in actions(env) if a["kind"] == "takedown_request"]) == 1


# ---------------- AWS keys ----------------
def aws_scan(env):
    inp = env.upload({"aws_config.py": fx("aws_config.py")})
    return env.scan(inp["input_id"], model_review=False)


def key_action(env, who="app"):
    return next(a for a in actions(env, who) if a["kind"] == "disable_aws_key")


def iam(env, deny_first=False):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
        calls.append((req, form))
        if deny_first and len(calls) == 1:
            return httpx.Response(403, content=f'<ErrorResponse xmlns="{IAM_NS}"><Error><Type>Sender</Type>'
                                                f'<Code>AccessDenied</Code><Message>no</Message></Error></ErrorResponse>')
        if form["Action"] == "GetAccessKeyLastUsed":
            return httpx.Response(200, content=f'<GetAccessKeyLastUsedResponse xmlns="{IAM_NS}"><GetAccessKeyLastUsedResult>'
                                                f'<UserName>deploy-bot</UserName><AccessKeyLastUsed><Region>N/A</Region>'
                                                f'</AccessKeyLastUsed></GetAccessKeyLastUsedResult></GetAccessKeyLastUsedResponse>')
        return httpx.Response(200, content=f'<UpdateAccessKeyResponse xmlns="{IAM_NS}"><ResponseMetadata><RequestId>r1'
                                            f'</RequestId></ResponseMetadata></UpdateAccessKeyResponse>')

    env.engine.remediation.gateway = Gateway(transport=httpx.MockTransport(handler), resolver=lambda h, p: ["52.94.225.248"])
    env.engine.remediation.env = {"TRACEFOLD_AWS_REMEDIATION_ACCESS_KEY_ID": REMEDIATION_KEY,
                                  "TRACEFOLD_AWS_REMEDIATION_SECRET_ACCESS_KEY": "remediation-secret-value-0000"}
    env.engine.remediation.clock = lambda: datetime(2026, 11, 7, 14, 0, tzinfo=timezone.utc)
    return calls


def test_aws_key_drafted_masked_and_needs_credentials(env):
    aws_scan(env)
    a = key_action(env)
    assert a["status"] == "drafted" and a["target"]["access_key_id"] == "****" + LEAKED[-4:]
    assert LEAKED not in json.dumps(actions(env))
    r = approve(env, a)
    assert r.status_code == 409 and r.json()["error"]["code"] == "aws_remediation_not_configured"
    status = env.client.get("/v1/capabilities", headers=env.h()).json()["remediation"]
    assert status == {"takedown_delivery": "outbox", "aws_key_disable": "not_configured"}


def test_aws_key_disabled_with_remediation_credentials_only(env):
    aws_scan(env)
    calls = iam(env)
    done = approve(env, key_action(env)).json()
    assert done["status"] == "completed" and done["result"] == {"aws_status": "Inactive", "iam_user": "deploy-bot"}
    (lookup, f1), (update, f2) = calls
    assert f1 == {"Action": "GetAccessKeyLastUsed", "AccessKeyId": LEAKED, "Version": "2010-05-08"}
    assert f2 == {"Action": "UpdateAccessKey", "AccessKeyId": LEAKED, "UserName": "deploy-bot", "Status": "Inactive",
                  "Version": "2010-05-08"}
    for req, _ in calls:
        auth = req.headers["authorization"]
        assert auth.startswith(f"AWS4-HMAC-SHA256 Credential={REMEDIATION_KEY}/20261107/us-east-1/iam/aws4_request")
        assert LEAKED not in auth  # the leaked key is never used to sign anything
    events = [e for e in ledger(env) if e["purpose"] == "aws_key_disable"]
    assert [e["payload_summary"]["api"] for e in events] == ["iam:GetAccessKeyLastUsed", "iam:UpdateAccessKey"]
    assert LEAKED not in json.dumps(events) and "remediation-secret" not in json.dumps(ledger(env))


def test_aws_access_denied_fails_then_retry_succeeds(env):
    aws_scan(env)
    iam(env, deny_first=True)
    failed = approve(env, key_action(env)).json()
    assert failed["status"] == "failed" and failed["result"]["error"]["code"] == "aws_access_denied"
    assert approve(env, failed).json()["status"] == "completed"


@pytest.mark.parametrize("who", ["reader", "cloud"])
def test_clients_without_approve_cannot_disable_keys(env, who):
    aws_scan(env)
    iam(env)
    assert approve(env, key_action(env), who=who).status_code == 403
    assert key_action(env)["status"] == "drafted"
