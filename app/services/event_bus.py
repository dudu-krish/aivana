"""Per-customer event bus — each buyer only sees their own agent activity."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AgentEvent:
    user_id: str
    agent_id: str
    agent_name: str
    event_type: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class EventBus:
    def __init__(self, max_history: int = 500) -> None:
        self._history: dict[str, deque[AgentEvent]] = defaultdict(
            lambda: deque(maxlen=max_history)
        )
        self._subscribers: dict[str, list[asyncio.Queue[AgentEvent]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def emit(
        self,
        user_id: str,
        agent_id: str,
        agent_name: str,
        event_type: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> AgentEvent:
        event = AgentEvent(
            user_id=user_id,
            agent_id=agent_id,
            agent_name=agent_name,
            event_type=event_type,
            message=message,
            data=data or {},
        )
        if event_type in ("completed", "error"):
            from app.services.result_queue import enqueue_from_event

            result_id = enqueue_from_event(event)
            event.data = {**event.data, "result_id": result_id}
        async with self._lock:
            self._history[user_id].append(event)
            for queue in self._subscribers[user_id]:
                await queue.put(event)
        return event

    def history(self, user_id: str) -> list[dict[str, Any]]:
        return [asdict(e) for e in self._history[user_id]]

    async def subscribe(self, user_id: str) -> asyncio.Queue[AgentEvent]:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        async with self._lock:
            self._subscribers[user_id].append(queue)
        return queue

    async def unsubscribe(self, user_id: str, queue: asyncio.Queue[AgentEvent]) -> None:
        async with self._lock:
            subs = self._subscribers[user_id]
            if queue in subs:
                subs.remove(queue)


event_bus = EventBus()
