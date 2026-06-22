"""Persistent per-user queue of agent execution results."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.services.database import (
    clear_agent_results,
    get_agent_result,
    list_agent_results,
    save_agent_result,
)
from app.services.event_bus import AgentEvent
from app.services.run_context import current_run_id


def enqueue_from_event(event: AgentEvent) -> str:
    """Store a completed or failed agent run in the results queue."""
    result_id = f"res-{uuid.uuid4().hex[:12]}"
    run_id = (event.data or {}).get("run_id") or current_run_id.get()
    payload = {
        "event_type": event.event_type,
        **(event.data or {}),
    }
    save_agent_result(
        result_id=result_id,
        user_id=event.user_id,
        agent_id=event.agent_id,
        agent_name=event.agent_name,
        status="error" if event.event_type == "error" else "completed",
        message=event.message,
        result=payload,
        run_id=run_id,
        created_at=event.timestamp,
    )
    return result_id


def list_results(
    user_id: str,
    *,
    limit: int = 50,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    return list_agent_results(user_id, limit=limit, agent_id=agent_id)


def get_result(user_id: str, result_id: str) -> dict[str, Any] | None:
    row = get_agent_result(user_id, result_id)
    if not row:
        return None
    return row


def latest_for_agent(user_id: str, agent_id: str) -> dict[str, Any] | None:
    rows = list_agent_results(user_id, limit=100, agent_id=agent_id)
    return rows[0] if rows else None


def clear_user_queue(user_id: str) -> int:
    return clear_agent_results(user_id)
