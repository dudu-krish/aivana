"""Telecaller agent — places outbound calls and speaks a greeting."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.sax.saxutils
from typing import Any

from app.agents.base import BaseAgent
from app.config import settings
from app.services.event_bus import event_bus
from app.services.tenant import TenantContext

AGENT_ID = "telecaller"
AGENT_NAME = "Telecaller"

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


def _twilio_configured() -> bool:
    return bool(
        settings.twilio_account_sid.strip()
        and settings.twilio_auth_token.strip()
        and settings.twilio_from_number.strip()
    )


def _place_twilio_call(to_number: str, message: str) -> dict[str, Any]:
    account_sid = settings.twilio_account_sid.strip()
    auth_token = settings.twilio_auth_token.strip()
    from_number = settings.twilio_from_number.strip()
    safe_message = xml.sax.saxutils.escape(message)
    twiml = f"<Response><Say voice=\"alice\">{safe_message}</Say></Response>"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
    payload = urllib.parse.urlencode(
        {"To": to_number, "From": from_number, "Twiml": twiml}
    ).encode()
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


class TelecallerAgent(BaseAgent):
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
        raw_calls = kwargs.get("calls") or []

        call_list: list[dict[str, str]] = []
        if raw_calls:
            for item in raw_calls:
                if not isinstance(item, dict):
                    continue
                normalized = _normalize_phone(str(item.get("phone_number", "")))
                if not normalized:
                    continue
                call_list.append(
                    {
                        "phone_number": normalized,
                        "message": str(item.get("message") or default_message).strip()
                        or default_message,
                        "customer_name": str(item.get("customer_name") or ""),
                    }
                )

        if not call_list:
            raw_numbers = kwargs.get("phone_numbers") or []
            for item in raw_numbers:
                normalized = _normalize_phone(str(item))
                if normalized:
                    call_list.append(
                        {
                            "phone_number": normalized,
                            "message": default_message,
                            "customer_name": "",
                        }
                    )

        if not call_list:
            await self._emit(
                "error",
                "No valid phone numbers. The planner did not identify any callback numbers.",
            )
            return {"status": "error", "message": "No phone numbers"}

        await self._emit(
            "started",
            f"Calling {len(call_list)} customer(s)",
            {"calls": call_list},
        )

        simulated = not _twilio_configured()
        if simulated:
            await self._emit(
                "progress",
                "Twilio not configured — simulating calls (set TWILIO_* in .env for live calls).",
            )

        results: list[dict[str, Any]] = []
        for call in call_list:
            number = call["phone_number"]
            message = call["message"]
            label = call.get("customer_name") or number
            try:
                if simulated:
                    await asyncio.sleep(0.6)
                    await self._emit(
                        "progress",
                        f"Simulated call to {label} ({number}): \"{message}\"",
                    )
                    results.append({"number": number, "status": "simulated", "message": message})
                else:
                    placed = await asyncio.to_thread(_place_twilio_call, number, message)
                    sid = placed.get("sid", "unknown")
                    await self._emit("progress", f"Call placed to {label} ({number}) SID: {sid}")
                    results.append({"number": number, "status": "queued", "sid": sid, "message": message})
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:200]
                await self._emit("error", f"Call failed for {number}: {detail}")
                results.append({"number": number, "status": "error", "detail": detail})
            except Exception as exc:
                await self._emit("error", f"Call failed for {number}: {exc}")
                results.append({"number": number, "status": "error", "detail": str(exc)})

        ok = sum(1 for r in results if r["status"] in {"queued", "simulated"})
        summary = f"Completed {ok}/{len(call_list)} call(s)"
        await self._emit("completed", summary, {"results": results, "simulated": simulated})
        return {"status": "completed", "results": results, "simulated": simulated}
