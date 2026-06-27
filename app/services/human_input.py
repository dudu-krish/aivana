"""Human-in-the-loop — pause agents until the user answers questions or approves output."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.event_bus import event_bus

DEFAULT_TIMEOUT_SECONDS = 3600


@dataclass
class HumanInputRequest:
    request_id: str
    user_id: str
    agent_id: str
    agent_name: str
    phase: str  # "input" | "review"
    questions: list[dict[str, Any]]
    draft_output: dict[str, Any] | None = None
    run_id: str | None = None
    answers: dict[str, Any] = field(default_factory=dict)


_pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
_requests: dict[str, HumanInputRequest] = {}
_user_pending: dict[str, list[str]] = {}


def list_pending(user_id: str) -> list[dict[str, Any]]:
    ids = _user_pending.get(user_id, [])
    out: list[dict[str, Any]] = []
    for rid in ids:
        req = _requests.get(rid)
        if req and rid in _pending and not _pending[rid].done():
            out.append(_request_payload(req))
    return out


def _request_payload(req: HumanInputRequest) -> dict[str, Any]:
    return {
        "request_id": req.request_id,
        "agent_id": req.agent_id,
        "agent_name": req.agent_name,
        "phase": req.phase,
        "questions": req.questions,
        "draft_output": req.draft_output,
        "run_id": req.run_id,
    }


def cancel_pending_human_input(user_id: str) -> None:
    """Unblock any agents waiting on human input for this user."""
    from app.services.run_control import AgentCancelledError

    for rid, req in list(_requests.items()):
        if req.user_id != user_id:
            continue
        fut = _pending.get(rid)
        if fut and not fut.done():
            fut.set_exception(AgentCancelledError("Stopped by user"))


async def request_human_input(
    user_id: str,
    agent_id: str,
    agent_name: str,
    *,
    phase: str,
    questions: list[dict[str, Any]],
    draft_output: dict[str, Any] | None = None,
    run_id: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Block until the user submits answers via POST /api/agents/human-input/respond."""
    request_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    future: asyncio.Future[dict[str, Any]] = loop.create_future()
    req = HumanInputRequest(
        request_id=request_id,
        user_id=user_id,
        agent_id=agent_id,
        agent_name=agent_name,
        phase=phase,
        questions=questions,
        draft_output=draft_output,
        run_id=run_id,
    )
    _pending[request_id] = future
    _requests[request_id] = req
    _user_pending.setdefault(user_id, []).append(request_id)

    phase_label = "Review output" if phase == "review" else "Your input needed"
    payload = _request_payload(req)
    await event_bus.emit(
        user_id,
        agent_id,
        agent_name,
        "awaiting_input",
        f"{phase_label} — {agent_name}",
        payload,
    )
    await event_bus.emit(
        user_id,
        agent_id,
        agent_name,
        "progress",
        f"⏸ Paused — waiting for you to answer ({phase}). Open the panel at the bottom of the screen.",
        {"hitl": payload, "request_id": request_id},
    )

    try:
        from app.services.run_control import AgentCancelledError, is_agent_cancelled

        poll = 0.5
        elapsed = 0.0
        while elapsed < timeout_seconds:
            if is_agent_cancelled(user_id, agent_id) or (
                agent_id.startswith("content-") and is_agent_cancelled(user_id, "content-director")
            ):
                if not future.done():
                    future.cancel()
                raise AgentCancelledError(f"Agent {agent_id} was stopped")
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout=poll)
            except asyncio.TimeoutError:
                elapsed += poll
        raise asyncio.TimeoutError("Human input timed out")
    finally:
        _pending.pop(request_id, None)
        _requests.pop(request_id, None)
        if user_id in _user_pending:
            _user_pending[user_id] = [r for r in _user_pending[user_id] if r != request_id]


def submit_human_input(user_id: str, request_id: str, answers: dict[str, Any]) -> bool:
    req = _requests.get(request_id)
    if not req or req.user_id != user_id:
        return False
    future = _pending.get(request_id)
    if not future or future.done():
        return False
    req.answers = dict(answers)
    future.set_result(dict(answers))
    return True
