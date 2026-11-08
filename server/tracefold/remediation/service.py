"""Remediation actions: drafted automatically from findings, executed only after a named person approves.

- ``takedown_request`` is drafted for every public-exposure finding. On approval it is emailed to the host's
  operator-configured abuse/legal contact, or, for hosts that only take requests through their own web form, it
  becomes ``awaiting_manual_submission`` with the form link and the prefilled text. "Submitted" never means removed:
  ``removal_observed`` turns true only after a fresh public scan no longer finds the passage at that URL.
- ``disable_aws_key`` is drafted for every long-term AWS access key ID found in a scanned file. On approval the
  key is set Inactive in IAM using the company's remediation credentials (never the leaked key). No replacement
  key is created.

Coding assistants are not given the ``approve`` capability by default, so they can read actions but not approve them.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ..contracts.enums import ActionKind, ActionStatus, Capability, Disclosure, FindingKind, FindingStatus
from ..contracts.models import (
    ActionDelivery, ActionOut, ActionPage, ApproveRequest, EditActionRequest, MarkSubmittedRequest, RejectRequest,
)
from ..errors import ApiError, not_found
from ..gateway.gateway import Gateway, mask_secret
from ..policy.auth import Principal
from ..util import iso, new_id, now
from . import aws, mailer, takedown

if TYPE_CHECKING:
    from ..engine import Engine
    from ..jobs.pipeline import ScanContext

log = logging.getLogger("tracefold.remediation")


def _version_conflict() -> ApiError:
    return ApiError(409, "version_conflict", "This action changed since you loaded it. Reload and try again.")


class RemediationService:
    def __init__(self, engine: "Engine", env: dict[str, str] | None = None, gateway: Gateway | None = None):
        self.e = engine
        self.env = env if env is not None else os.environ
        self.gateway = gateway or Gateway()
        self.clock = None  # test seam for AWS request timestamps

    @property
    def mail_transport(self) -> str:
        return self.env.get("TRACEFOLD_MAIL_TRANSPORT", "outbox")

    def status(self) -> dict[str, str]:
        return {"takedown_delivery": mailer.transport_status(self.mail_transport, self.env),
                "aws_key_disable": "configured" if aws.AwsCredentials.from_env(self.env) else "not_configured"}

    # ---------------- drafting (runs inside a scan, after publication) ----------------
    def draft_for_scan(self, ctx: "ScanContext", published: list[tuple[str, str]]) -> int:
        drafted = 0
        ws = ctx.scan["workspace_id"]
        for p, (finding_id, _obs) in zip(ctx.candidates, published):
            rec = None
            if p.kind == FindingKind.public_exposure.value and p.evidence:
                rec = self._takedown_record(ws, finding_id, p.evidence[0])
            elif p.rule_id == "secret_literal" and p.meta.get("pattern") == "aws_access_key_id":
                key = next((v for v in p.secret_values if aws.ACCESS_KEY_ID.match(v)), None)
                if key:
                    rec = self._record(ws, finding_id, ActionKind.disable_aws_key, {"access_key_id": key}, {})
            if rec and self.e.repo.insert_action_if_absent(rec):
                drafted += 1
        return drafted

    def _record(self, ws: str, finding_id: str, kind: ActionKind, target: dict, draft: dict) -> dict:
        t = iso(now())
        return {"id": new_id("act"), "workspace_id": ws, "finding_id": finding_id, "kind": kind.value,
                "status": ActionStatus.drafted.value, "target": target, "draft": draft, "result": {},
                "created_at": t, "updated_at": t}

    def _takedown_record(self, ws: str, finding_id: str, ev: dict) -> dict | None:
        pub = ev.get("public") or {}
        if pub.get("mode") == "discovered":
            # Found by searching a company name, which may not be this workspace's company. A takedown asserts
            # ownership, so it is only drafted for operator-approved sources, never for search results.
            return None
        url = pub.get("url")
        host = (urlsplit(url or "").hostname or "").lower()
        if not url or not host:
            return None
        text = self.e.retrieval.blobs.read(ev["public_blob"]) if ev.get("public_blob") else None
        quoted = takedown.excerpt(text[pub["start"]:pub["end"]]) if text else ""
        if not quoted:
            return None
        target = {"url": url, "host": host, "source_id": pub.get("source_id"), "excerpt": quoted,
                  "retrieved_at": pub.get("retrieved_at")}
        return self._record(ws, finding_id, ActionKind.takedown_request, target,
                            takedown.draft(host, url, quoted, pub.get("retrieved_at")))

    # ---------------- reading ----------------
    def _action_in_ws(self, ws_id: str, action_id: str) -> dict:
        a = self.e.repo.get_action(action_id)
        if a is None or a["workspace_id"] != ws_id:
            raise not_found()
        return a

    def _delivery(self, ws_id: str, a: dict) -> ActionDelivery | None:
        if a["kind"] != ActionKind.takedown_request.value:
            return None
        c = self.e.repo.get_takedown_contact(ws_id, a["target"]["host"])
        if c is None:
            return ActionDelivery(method="none")
        if c["method"] == "email":
            return ActionDelivery(method="email", address=c["address"], transport=self.mail_transport)
        return ActionDelivery(method="form", form_url=c["address"])

    def out(self, a: dict, disclosure: Disclosure) -> ActionOut:
        minimal = disclosure != Disclosure.full
        ws = a["workspace_id"]
        target = dict(a["target"])
        subject = body = draft_body = None
        removal = None
        if a["kind"] == ActionKind.takedown_request.value:
            summary = f"Ask {target['host']} to remove the copied content"
            profile = self.e.repo.get_remediation_profile(ws)
            if not minimal:
                subject = a["draft"].get("subject")
                draft_body = a["draft"].get("body")
                company = profile["company_name"] if profile else "[company name not set]"
                reply_to = profile["reply_to"] if profile else "[reply-to not set]"
                body = takedown.render(a["draft"].get("body", ""), company, reply_to, a.get("approver"))
            else:
                target.pop("excerpt", None)
            f = self.e.repo.get_finding(a["finding_id"])
            if a["status"] in (ActionStatus.submitted.value, ActionStatus.awaiting_manual_submission.value):
                removal = bool(f and f["status"] == FindingStatus.no_longer_observed.value)
        else:
            target["access_key_id"] = mask_secret(target["access_key_id"])
            summary = f"Disable AWS access key {target['access_key_id']}"
        approver = a.get("approver")
        if approver and minimal:
            approver = {"name": approver.get("name")}
        return ActionOut(
            action_id=a["id"], workspace_id=ws, finding_id=a["finding_id"], kind=a["kind"], status=a["status"],
            version=a["version"], summary=summary, target=target, delivery=self._delivery(ws, a), subject=subject,
            body=body, draft_body=draft_body, approver=approver, approved_at=a.get("approved_at"), executed_at=a.get("executed_at"),
            result=a.get("result") or {}, removal_observed=removal, created_at=a["created_at"], updated_at=a["updated_at"],
        )

    def list(self, p: Principal, ws_id: str, status: str | None, finding_id: str | None, cursor: str | None,
             limit: int) -> ActionPage:
        g = p.require(ws_id, Capability.read)
        if status and status not in {s.value for s in ActionStatus}:
            raise ApiError(422, "invalid_request", "Unknown action status.")
        rows = self.e.repo.list_actions(ws_id, status, finding_id, cursor, limit + 1)
        return ActionPage(items=[self.out(a, g.disclosure) for a in rows[:limit]],
                          next_cursor=rows[limit - 1]["id"] if len(rows) > limit else None)

    def get(self, p: Principal, ws_id: str, action_id: str) -> ActionOut:
        g = p.require(ws_id, Capability.read)
        return self.out(self._action_in_ws(ws_id, action_id), g.disclosure)

    # ---------------- decisions ----------------
    def edit(self, p: Principal, ws_id: str, action_id: str, req: EditActionRequest) -> ActionOut:
        g = p.require(ws_id, Capability.approve)
        a = self._action_in_ws(ws_id, action_id)
        if a["kind"] != ActionKind.takedown_request.value or a["status"] not in (ActionStatus.drafted.value,
                                                                                  ActionStatus.failed.value):
            raise ApiError(409, "invalid_state", "Only takedown requests that haven't been sent can be edited.")
        draft = dict(a["draft"])
        if req.subject is not None:
            draft["subject"] = req.subject
        if req.body is not None:
            draft["body"] = req.body
        if not self.e.repo.update_action(a["id"], req.expected_version, draft=draft):
            raise _version_conflict()
        return self.out(self.e.repo.get_action(a["id"]), g.disclosure)

    def reject(self, p: Principal, ws_id: str, action_id: str, req: RejectRequest) -> ActionOut:
        g = p.require(ws_id, Capability.approve)
        a = self._action_in_ws(ws_id, action_id)
        if a["status"] not in (ActionStatus.drafted.value, ActionStatus.failed.value):
            raise ApiError(409, "invalid_state", f"This action is already {a['status']}.")
        if not self.e.repo.update_action(a["id"], req.expected_version, status=ActionStatus.rejected.value,
                                         result={"rejected_by": p.name, "reason": req.reason}):
            raise _version_conflict()
        return self.out(self.e.repo.get_action(a["id"]), g.disclosure)

    def mark_submitted(self, p: Principal, ws_id: str, action_id: str, req: MarkSubmittedRequest) -> ActionOut:
        g = p.require(ws_id, Capability.approve)
        a = self._action_in_ws(ws_id, action_id)
        if a["status"] != ActionStatus.awaiting_manual_submission.value:
            raise ApiError(409, "invalid_state", "Only requests waiting for a web-form submission can be marked submitted.")
        result = {**(a.get("result") or {}), "submitted_via": "host_form", "note": req.note}
        if not self.e.repo.update_action(a["id"], req.expected_version, status=ActionStatus.submitted.value,
                                         executed_at=iso(now()), result=result):
            raise _version_conflict()
        return self.out(self.e.repo.get_action(a["id"]), g.disclosure)

    def approve(self, p: Principal, ws_id: str, action_id: str, req: ApproveRequest) -> ActionOut:
        g = p.require(ws_id, Capability.approve)
        a = self._action_in_ws(ws_id, action_id)
        if a["status"] not in (ActionStatus.drafted.value, ActionStatus.failed.value):
            raise ApiError(409, "invalid_state", f"This action is already {a['status']}.")
        if a["version"] != req.expected_version:
            raise _version_conflict()
        if not req.attest_authorized:
            raise ApiError(422, "attestation_required",
                           "Confirm that you're authorized to act for the company before approving.")
        approver = {**req.approver.model_dump(), "client": p.name}
        if a["kind"] == ActionKind.takedown_request.value:
            self._approve_takedown(ws_id, a, approver)
        else:
            self._approve_aws(a, approver)
        return self.out(self.e.repo.get_action(a["id"]), g.disclosure)

    def _begin(self, a: dict, approver: dict) -> int:
        """Claim the action for execution. Returns the new version; a concurrent approval gets a conflict."""
        if not self.e.repo.update_action(a["id"], a["version"], status=ActionStatus.executing.value, approver=approver,
                                         approved_at=iso(now())):
            raise _version_conflict()
        return a["version"] + 1

    def _finish(self, a: dict, version: int, status: ActionStatus, result: dict) -> None:
        self.e.repo.update_action(a["id"], version, status=status.value, executed_at=iso(now()), result=result)

    def _approve_takedown(self, ws_id: str, a: dict, approver: dict) -> None:
        profile = self.e.repo.get_remediation_profile(ws_id)
        if profile is None:
            raise ApiError(409, "remediation_profile_missing",
                           "Set the company name and reply-to address first (tracefold set-remediation-profile).")
        contact = self.e.repo.get_takedown_contact(ws_id, a["target"]["host"])
        if contact is None:
            raise ApiError(409, "no_takedown_contact",
                           f"Add a takedown contact for {a['target']['host']} first (tracefold add-takedown-contact).")
        if contact["method"] == "form":
            ok = self.e.repo.update_action(a["id"], a["version"], status=ActionStatus.awaiting_manual_submission.value,
                                           approver=approver, approved_at=iso(now()),
                                           result={"form_url": contact["address"]})
            if not ok:
                raise _version_conflict()
            return
        version = self._begin(a, approver)
        body = takedown.render(a["draft"]["body"], profile["company_name"], profile["reply_to"], approver)
        msg = mailer.Message(to=contact["address"], reply_to=profile["reply_to"], subject=a["draft"]["subject"], body=body)
        before = len(self.gateway.ledger)
        try:
            result = mailer.send(msg, self.mail_transport, self.env, self.gateway, self.e.settings.data_dir / "outbox", a["id"])
        except mailer.DeliveryError as ex:
            self._finish(a, version, ActionStatus.failed, {"error": {"code": ex.code, "message": ex.message}})
        except Exception as ex:  # never leave an approved action stuck in "executing"
            log.error("takedown delivery failed: %s", type(ex).__name__)
            self._finish(a, version, ActionStatus.failed, {"error": {"code": "internal_error", "message": "Sending failed."}})
        else:
            self._finish(a, version, ActionStatus.submitted, {**result, "sent_to": contact["address"]})
        finally:
            self._persist_ledger(ws_id, before, outbox=self.mail_transport == "outbox", action_id=a["id"])

    def _approve_aws(self, a: dict, approver: dict) -> None:
        creds = aws.AwsCredentials.from_env(self.env)
        if creds is None:
            raise ApiError(409, "aws_remediation_not_configured",
                           f"Set {aws.ENV_KEY_ID} and {aws.ENV_SECRET} for a remediation IAM principal on the engine.")
        version = self._begin(a, approver)
        before = len(self.gateway.ledger)
        try:
            result = aws.disable_key(creds, self.gateway, a["target"]["access_key_id"], clock=self.clock)
        except aws.AwsActionError as ex:
            self._finish(a, version, ActionStatus.failed, {"error": {"code": ex.code, "message": ex.message}})
        except Exception as ex:
            log.error("aws key disable failed: %s", type(ex).__name__)
            self._finish(a, version, ActionStatus.failed, {"error": {"code": "internal_error", "message": "Disabling failed."}})
        else:
            self._finish(a, version, ActionStatus.completed, result)
        finally:
            self._persist_ledger(a["workspace_id"], before)

    def _persist_ledger(self, ws_id: str, before: int, outbox: bool = False, action_id: str | None = None) -> None:
        events = [{**ev, "workspace_id": ws_id} for ev in self.gateway.ledger[before:]]
        if outbox:
            events.append({"id": new_id("ev"), "workspace_id": ws_id, "destination_category": "local_outbox",
                           "destination_host": "outbox", "purpose": "takedown_request", "source_id": None,
                           "status": "written", "payload_summary": {"action_id": action_id}, "at": iso(now())})
        self.e.repo.insert_ledger(events)
