"""Outbound delivery channels: SMTP email, SMS (Twilio / MSG91 DLT), Web Push (VAPID)."""

from __future__ import annotations

import json
import logging
from email.message import EmailMessage
from html import escape

import aiosmtplib
import anyio
import httpx
from pywebpush import WebPushException, webpush

from app.core.config import get_settings
from app.core.metrics import NOTIFICATIONS_SENT

logger = logging.getLogger(__name__)


def _html_email(title: str, body: str, link: str | None) -> str:
    s = get_settings()
    button = (
        f'<p><a href="{escape(s.public_web_url + link)}" style="background:#0f5132;color:#fff;padding:10px 18px;'
        f'border-radius:8px;text-decoration:none">Open in Lumen</a></p>'
        if link
        else ""
    )
    paragraphs = "".join(f"<p>{escape(p)}</p>" for p in body.split("\n") if p.strip())
    return (
        '<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#1f2933">'
        '<div style="background:#0b3d2e;color:#fff;padding:14px 20px;border-radius:10px 10px 0 0">'
        "<strong>Lumen</strong> · Ministry of Coal</div>"
        f'<div style="border:1px solid #e5e7eb;border-top:0;padding:20px;border-radius:0 0 10px 10px">'
        f"<h2 style=\"margin-top:0\">{escape(title)}</h2>{paragraphs}{button}"
        '<p style="color:#6b7280;font-size:12px">This is an automated governance notification. '
        "Do not reply.</p></div></div>"
    )


async def send_email(to: str, subject: str, body: str, link: str | None = None) -> bool:
    s = get_settings()
    if not s.email_enabled:
        return False
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body + (f"\n\n{s.public_web_url}{link}" if link else ""))
    msg.add_alternative(_html_email(subject, body, link), subtype="html")
    try:
        await aiosmtplib.send(
            msg,
            hostname=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_username,
            password=s.smtp_password.get_secret_value() if s.smtp_password else None,
            start_tls=s.smtp_starttls and not s.smtp_use_tls,
            use_tls=s.smtp_use_tls,
            timeout=20,
        )
        NOTIFICATIONS_SENT.labels("email", "ok").inc()
        return True
    except Exception as exc:
        NOTIFICATIONS_SENT.labels("email", "error").inc()
        logger.warning("email delivery failed: %s", exc)
        return False


def _normalise_msisdn(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits  # Indian mobile default
    return digits


async def send_sms(phone: str, text: str) -> bool:
    s = get_settings()
    if s.sms_provider == "none" or not phone:
        return False
    msisdn = _normalise_msisdn(phone)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if s.sms_provider == "twilio":
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
                    auth=(s.twilio_account_sid or "", s.twilio_auth_token.get_secret_value() if s.twilio_auth_token else ""),
                    data={"To": f"+{msisdn}", "From": s.twilio_from_number, "Body": text[:1500]},
                )
            else:  # MSG91 Flow API with a DLT-approved template (mandatory in India)
                resp = await client.post(
                    "https://control.msg91.com/api/v5/flow",
                    headers={"authkey": s.msg91_auth_key.get_secret_value() if s.msg91_auth_key else ""},
                    json={"template_id": s.msg91_template_id, "recipients": [{"mobiles": msisdn, "message": text[:300]}]},
                )
        ok = resp.status_code < 300
        NOTIFICATIONS_SENT.labels("sms", "ok" if ok else "error").inc()
        if not ok:
            logger.warning("sms provider error %s: %s", resp.status_code, resp.text[:200])
        return ok
    except httpx.HTTPError as exc:
        NOTIFICATIONS_SENT.labels("sms", "error").inc()
        logger.warning("sms delivery failed: %s", exc)
        return False


async def send_push(endpoint: str, p256dh: str, auth: str, payload: dict) -> str:
    """Returns 'ok', 'gone' (subscription expired → delete it) or 'error'."""
    s = get_settings()
    if not (s.vapid_private_key and s.vapid_public_key):
        return "error"

    def _send() -> str:
        try:
            webpush(
                subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
                data=json.dumps(payload),
                vapid_private_key=s.vapid_private_key.get_secret_value(),  # type: ignore[union-attr]
                vapid_claims={"sub": s.vapid_subject},
                ttl=3600,
                timeout=10,
            )
            return "ok"
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            return "gone" if status in (404, 410) else "error"

    result = await anyio.to_thread.run_sync(_send)
    NOTIFICATIONS_SENT.labels("push", result).inc()
    return result
