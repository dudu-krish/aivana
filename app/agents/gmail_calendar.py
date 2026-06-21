"""Gmail Calendar agent — list and create Google Calendar events."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.services.event_bus import event_bus
from app.services.gmail_auth import get_calendar_service
from app.services.tenant import TenantContext

AGENT_ID = "gmail-calendar"
AGENT_NAME = "Gmail Calendar"


def _parse_day(value: str | None, default: date) -> date:
    if not value:
        return default
    raw = str(value).strip()[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return default


def _to_rfc3339(day: date, hour: int = 0, minute: int = 0) -> str:
    dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
    return dt.isoformat()


class GmailCalendarAgent(BaseAgent):
    agent_id = AGENT_ID
    agent_name = AGENT_NAME

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, AGENT_ID, AGENT_NAME, event_type, message, data
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        action = str(kwargs.get("action") or "list_events").strip()
        today = date.today()
        date_from = _parse_day(kwargs.get("date_from"), today)
        date_to = _parse_day(kwargs.get("date_to"), date_from + timedelta(days=7))
        if date_to < date_from:
            date_to = date_from

        await self._emit("started", f"Calendar action: {action}")

        try:
            service = get_calendar_service(self.tenant)
        except FileNotFoundError as exc:
            await self._emit("error", str(exc))
            return {"status": "error", "message": str(exc), "auth_required": True}
        except Exception as exc:
            await self._emit("error", f"Calendar auth failed: {exc}")
            return {"status": "error", "message": str(exc), "auth_required": True}

        if action == "create_event":
            return await self._create_event(service, kwargs)
        return await self._list_events(service, date_from, date_to, kwargs)

    async def _list_events(
        self,
        service: Any,
        date_from: date,
        date_to: date,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        max_results = int(kwargs.get("max_results") or 25)
        time_min = _to_rfc3339(date_from)
        time_max = _to_rfc3339(date_to + timedelta(days=1))

        await self._emit(
            "progress",
            f"Fetching events from {date_from.isoformat()} to {date_to.isoformat()}",
        )

        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events: list[dict[str, Any]] = []
        for item in result.get("items", []):
            start = item.get("start", {})
            end = item.get("end", {})
            summary = item.get("summary", "(no title)")
            event = {
                "id": item.get("id"),
                "summary": summary,
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "location": item.get("location", ""),
                "attendees": [
                    a.get("email") for a in item.get("attendees", []) if a.get("email")
                ],
            }
            events.append(event)
            await self._emit("progress", f"Event: {summary}")

        msg = f"Found {len(events)} event(s)"
        await self._emit("completed", msg, {"events": events})
        return {
            "status": "completed",
            "action": "list_events",
            "events": events,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }

    async def _create_event(self, service: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        title = str(kwargs.get("event_title") or "Meeting").strip() or "Meeting"
        start_raw = str(kwargs.get("event_start") or "").strip()
        duration = int(kwargs.get("event_duration_minutes") or 30)
        attendees = [str(a).strip() for a in (kwargs.get("attendees") or []) if str(a).strip()]

        if start_raw:
            try:
                if "T" in start_raw:
                    start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                else:
                    start_dt = datetime.fromisoformat(start_raw + "T10:00:00").replace(
                        tzinfo=timezone.utc
                    )
            except ValueError:
                start_dt = datetime.now(timezone.utc) + timedelta(hours=1)
        else:
            start_dt = datetime.now(timezone.utc) + timedelta(hours=1)

        end_dt = start_dt + timedelta(minutes=duration)
        body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
        }
        if attendees:
            body["attendees"] = [{"email": addr} for addr in attendees]

        await self._emit("progress", f"Creating event: {title}")
        created = (
            service.events()
            .insert(calendarId="primary", body=body, sendUpdates="none")
            .execute()
        )

        event_id = created.get("id", "")
        link = created.get("htmlLink", "")
        await self._emit(
            "completed",
            f"Created event \"{title}\"",
            {"event_id": event_id, "link": link},
        )
        return {
            "status": "completed",
            "action": "create_event",
            "event_id": event_id,
            "link": link,
            "summary": title,
        }
