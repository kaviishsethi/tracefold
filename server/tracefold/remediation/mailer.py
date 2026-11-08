"""Delivery for approved takedown emails.

Two transports:
- ``outbox`` (default): writes the message as an .eml file under ``<data>/outbox``. Nothing leaves the machine.
  Use it for local evaluation and tests, or to send from your own mail client.
- ``resend``: sends through the Resend HTTP API via the engine gateway. Needs ``RESEND_API_KEY`` and
  ``TRACEFOLD_MAIL_FROM`` (a sender on a domain verified with Resend).
"""
from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from ..gateway.gateway import Gateway, GatewayDenied, Policy

RESEND_URL = "https://api.resend.com/emails"
RESEND_POLICY = Policy(category="takedown_email", purpose="takedown_request", allowed_hosts=frozenset({"api.resend.com"}),
                       max_request_bytes=64 * 1024, max_response_bytes=16 * 1024, timeout=20.0, max_redirects=0)


@dataclass
class Message:
    to: str
    reply_to: str
    subject: str
    body: str


class DeliveryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def transport_status(transport: str, env: dict[str, str]) -> str:
    if transport == "outbox":
        return "outbox"
    if transport == "resend":
        return "resend" if env.get("RESEND_API_KEY") and env.get("TRACEFOLD_MAIL_FROM") else "resend_not_configured"
    return "not_configured"


def send(msg: Message, transport: str, env: dict[str, str], gateway: Gateway, outbox_dir: Path, name: str) -> dict:
    """Deliver ``msg``. Returns a small result dict (no message body) to store on the action."""
    if transport == "outbox":
        em = EmailMessage()
        em["From"] = env.get("TRACEFOLD_MAIL_FROM") or "takedowns@tracefold.local"
        em["To"], em["Reply-To"], em["Subject"] = msg.to, msg.reply_to, msg.subject
        em["Message-ID"] = make_msgid(domain="tracefold.local")
        em.set_content(msg.body)
        outbox_dir.mkdir(parents=True, exist_ok=True)
        path = outbox_dir / f"{name}.eml"
        path.write_bytes(bytes(em))
        return {"transport": "outbox", "message_id": em["Message-ID"], "outbox_file": path.name}
    if transport == "resend":
        key, sender = env.get("RESEND_API_KEY"), env.get("TRACEFOLD_MAIL_FROM")
        if not key or not sender:
            raise DeliveryError("mail_not_configured", "Set RESEND_API_KEY and TRACEFOLD_MAIL_FROM to send email.")
        try:
            r = gateway.request("POST", RESEND_URL, RESEND_POLICY, headers={"Authorization": f"Bearer {key}"},
                                json_body={"from": sender, "to": [msg.to], "reply_to": msg.reply_to,
                                           "subject": msg.subject, "text": msg.body},
                                summary={"recipient_domain": msg.to.rsplit("@", 1)[-1], "body_chars": len(msg.body)})
        except GatewayDenied as ex:
            raise DeliveryError("mail_unreachable", f"Could not reach the email service ({ex.reason}).") from None
        if r.status >= 300:
            raise DeliveryError("mail_rejected", f"The email service refused the message (HTTP {r.status}).")
        try:
            import json
            mid = json.loads(r.body).get("id")
        except ValueError:
            mid = None
        return {"transport": "resend", "message_id": mid}
    raise DeliveryError("mail_not_configured", f"Unknown mail transport {transport!r}.")
