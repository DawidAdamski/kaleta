# SPDX-License-Identifier: AGPL-3.0-or-later
"""Route a filed report to the maintainer, without a third-party error service.

Both routes are optional and env-driven. Delivery runs after the report is
committed and its failures stay in the log: a user who filed a report has
done their part, and a broken webhook is not their problem.
"""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx

from kaleta.config import settings

logger = logging.getLogger(__name__)

_WEBHOOK_TIMEOUT_SECONDS = 10.0
_SMTP_TIMEOUT_SECONDS = 15.0

#: asyncio keeps only a weak reference to a task, so a delivery in flight
#: would be collectable mid-await. Hold it until it finishes.
_in_flight: set[asyncio.Task[bool]] = set()


def webhook_url() -> str | None:
    return settings.bug_report_webhook or None


def webhook_includes_logs() -> bool:
    return bool(settings.bug_report_webhook_include_logs)


def email_recipient() -> str | None:
    if not settings.bug_report_email or not settings.smtp_host:
        return None
    return settings.bug_report_email


def _email_body(payload: dict[str, Any]) -> str:
    lines = [
        f"Report:   {payload.get('report_id')}",
        f"When:     {payload.get('created_at')}",
        f"Version:  {payload.get('app_version')}",
        f"Route:    {payload.get('route')}",
        f"Events:   {', '.join(payload.get('event_ids') or []) or '—'}",
        f"Contact:  {payload.get('contact_email') or '—'}",
        "",
        str(payload.get("summary") or ""),
        "",
        str(payload.get("description") or ""),
    ]
    return "\n".join(lines)


async def _post_webhook(url: str, payload: dict[str, Any]) -> bool:
    async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    return True


def _send_email_sync(recipient: str, payload: dict[str, Any]) -> bool:
    message = EmailMessage()
    message["Subject"] = f"[Kaleta] {payload.get('report_id')} — {payload.get('summary')}"
    message["From"] = settings.smtp_from or settings.smtp_username or recipient
    message["To"] = recipient
    message.set_content(_email_body(payload))

    host = settings.smtp_host or ""
    with smtplib.SMTP(host, settings.smtp_port, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return True


async def deliver(payload: dict[str, Any]) -> bool:
    """Send *payload* everywhere it is configured to go; never raise.

    Returns ``True`` when at least one route accepted it.
    """
    delivered = False

    url = webhook_url()
    if url:
        try:
            delivered = await _post_webhook(url, payload) or delivered
        except Exception:
            logger.exception("Bug report webhook delivery failed for %s", payload.get("report_id"))

    recipient = email_recipient()
    if recipient:
        try:
            delivered = await asyncio.to_thread(_send_email_sync, recipient, payload) or delivered
        except Exception:
            logger.exception("Bug report e-mail delivery failed for %s", payload.get("report_id"))

    if not url and not recipient:
        logger.debug(
            "No bug report delivery configured; %s stays in the database (%s bytes)",
            payload.get("report_id"),
            len(json.dumps(payload, default=str)),
        )
    return delivered


def schedule_delivery(payload: dict[str, Any]) -> None:
    """Fire delivery off the request path; nothing here reaches the UI."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("No running loop for bug report delivery; skipping")
        return
    task = loop.create_task(deliver(payload))
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)
