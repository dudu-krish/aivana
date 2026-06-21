"""WhatsApp agent — send outbound WhatsApp messages via Twilio."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.agents.base import BaseAgent
from app.config import settings
from app.services.event_bus import event_bus
from app.services.tenant import TenantContext

AGENT_ID = "whatsapp"
AGENT_NAME = "WhatsApp"

_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


def _normalize_phone(value: str) -> str | None:
    cleaned = re.sub(r"[\s\-().]", "", value.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if cleaned and not cleaned.startswith("+") and cleaned.isdigit():
        cleaned = "+" + cleaned
    if _PHONE_RE.match(cleaned):
        return cleaned
    return None


def _whatsapp_configured() -> bool:
    from_number = (
        settings.twilio_whatsapp_from.strip() or settings.twilio_from_number.strip()
    )
    return bool(
        settings.twilio_account_sid.strip()
        and settings.twilio_auth_token.strip()
        and from_number
    )


def _whatsapp_from() -> str:
    raw = settings.twilio_whatsapp_from.strip() or settings.twilio_from_number.strip()
    if raw.startswith("whatsapp:"):
        return raw
    return f"whatsapp:{raw}"


def _send_twilio_whatsapp(to_number: str, message: str) -> dict[str, Any]:
    account_sid = settings.twilio_account_sid.strip()
    auth_token = settings.twilio_auth_token.strip()
    from_addr = _whatsapp_from()
    to_addr = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = urllib.parse.urlencode(
        {"To": to_addr, "From": from_addr, "Body": message}
    ).encode()
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


class WhatsAppAgent(BaseAgent):
    agent_id = AGENT_ID
    agent_name = AGENT_NAME

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, AGENT_ID, AGENT_NAME, event_type, message, data
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        default_message = str(kwargs.get("message") or "Hello").strip() or "Hello"
        raw_messages = kwargs.get("messages") or []

        send_list: list[dict[str, str]] = []
        if raw_messages:
            for item in raw_messages:
                if not isinstance(item, dict):
                    continue
                normalized = _normalize_phone(str(item.get("phone_number", "")))
                if not normalized:
                    continue
                send_list.append(
                    {
                        "phone_number": normalized,
                        "message": str(item.get("message") or default_message).strip()
                        or default_message,
                    }
                )

        if not send_list:
            for item in kwargs.get("phone_numbers") or []:
                normalized = _normalize_phone(str(item))
                if normalized:
                    send_list.append(
                        {"phone_number": normalized, "message": default_message}
                    )

        if not send_list:
            await self._emit(
                "error",
                "No valid WhatsApp numbers. Add phone numbers in the agent configuration.",
            )
            return {"status": "error", "message": "No phone numbers"}

        await self._emit(
            "started",
            f"Sending WhatsApp to {len(send_list)} recipient(s)",
            {"recipients": send_list},
        )

        simulated = not _whatsapp_configured()
        if simulated:
            await self._emit(
                "progress",
                "Twilio WhatsApp not configured — simulating (set TWILIO_* and TWILIO_WHATSAPP_FROM in .env).",
            )

        results: list[dict[str, Any]] = []
        for item in send_list:
            number = item["phone_number"]
            message = item["message"]
            try:
                if simulated:
                    await asyncio.sleep(0.5)
                    await self._emit(
                        "progress",
                        f"Simulated WhatsApp to {number}: \"{message[:80]}\"",
                    )
                    results.append({"number": number, "status": "simulated"})
                else:
                    sent = await asyncio.to_thread(_send_twilio_whatsapp, number, message)
                    sid = sent.get("sid", "unknown")
                    await self._emit("progress", f"WhatsApp sent to {number} SID: {sid}")
                    results.append({"number": number, "status": "sent", "sid": sid})
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:200]
                await self._emit("error", f"WhatsApp failed for {number}: {detail}")
                results.append({"number": number, "status": "error", "detail": detail})
            except Exception as exc:
                await self._emit("error", f"WhatsApp failed for {number}: {exc}")
                results.append({"number": number, "status": "error", "detail": str(exc)})

        ok = sum(1 for r in results if r["status"] in {"sent", "simulated"})
        summary = f"Delivered {ok}/{len(send_list)} WhatsApp message(s)"
        await self._emit("completed", summary, {"results": results, "simulated": simulated})
        return {"status": "completed", "results": results, "simulated": simulated}
