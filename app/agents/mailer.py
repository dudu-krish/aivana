"""Mailer agent — sends outbound emails."""

from __future__ import annotations

import asyncio
import re
import smtplib
from email.mime.text import MIMEText
from typing import Any

from app.agents.base import BaseAgent
from app.config import settings
from app.services.event_bus import event_bus
from app.services.tenant import TenantContext

AGENT_ID = "mailer"
AGENT_NAME = "Mailer"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str | None:
    addr = value.strip().lower()
    if _EMAIL_RE.match(addr):
        return addr
    return None


def _smtp_configured() -> bool:
    return bool(settings.smtp_host.strip() and settings.smtp_from.strip())


def _send_smtp(to_addrs: list[str], subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from.strip()
    msg["To"] = ", ".join(to_addrs)

    host = settings.smtp_host.strip()
    port = settings.smtp_port
    with smtplib.SMTP(host, port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        user = settings.smtp_user.strip()
        password = settings.smtp_password
        if user:
            server.login(user, password)
        server.sendmail(settings.smtp_from.strip(), to_addrs, msg.as_string())


class MailerAgent(BaseAgent):
    agent_id = AGENT_ID
    agent_name = AGENT_NAME

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, AGENT_ID, AGENT_NAME, event_type, message, data
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        raw_recipients = kwargs.get("to") or kwargs.get("recipients") or []
        subject = str(kwargs.get("subject") or "Hello").strip() or "Hello"
        body = str(kwargs.get("body") or "Hello").strip() or "Hello"

        recipients: list[str] = []
        for item in raw_recipients:
            normalized = _normalize_email(str(item))
            if normalized:
                recipients.append(normalized)

        if not recipients:
            await self._emit(
                "error",
                "No valid recipient emails. Add addresses in the agent configuration.",
            )
            return {"status": "error", "message": "No recipients"}

        await self._emit(
            "started",
            f"Sending \"{subject}\" to {len(recipients)} recipient(s)",
            {"to": recipients, "subject": subject},
        )

        simulated = not _smtp_configured()
        if simulated:
            await self._emit(
                "progress",
                "SMTP not configured — simulating send (set SMTP_* in .env for live emails).",
            )

        results: list[dict[str, Any]] = []
        if simulated:
            for addr in recipients:
                await asyncio.sleep(0.4)
                await self._emit("progress", f"Simulated email to {addr}: \"{subject}\"")
                results.append({"to": addr, "status": "simulated"})
        else:
            try:
                await asyncio.to_thread(_send_smtp, recipients, subject, body)
                for addr in recipients:
                    await self._emit("progress", f"Email sent to {addr}")
                    results.append({"to": addr, "status": "sent"})
            except Exception as exc:
                await self._emit("error", f"Email send failed: {exc}")
                return {"status": "error", "message": str(exc)}

        summary = f"Delivered {len(results)} email(s)"
        await self._emit("completed", summary, {"results": results, "simulated": simulated})
        return {"status": "completed", "results": results, "simulated": simulated}
