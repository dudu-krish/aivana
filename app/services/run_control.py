"""Cooperative cancellation for workflow and agent runs."""

from __future__ import annotations

_cancelled_agents: set[str] = set()
_cancelled_workflows: set[str] = set()


class AgentCancelledError(Exception):
    """Raised when an agent run is stopped by the user."""


def _agent_key(user_id: str, agent_id: str) -> str:
    return f"{user_id}:{agent_id}"


def _workflow_key(user_id: str, run_id: str | None = None) -> str:
    if run_id:
        return f"{user_id}:{run_id}"
    return user_id


def request_cancel_agent(user_id: str, agent_id: str) -> None:
    _cancelled_agents.add(_agent_key(user_id, agent_id))


def clear_agent_cancel(user_id: str, agent_id: str) -> None:
    _cancelled_agents.discard(_agent_key(user_id, agent_id))


def is_agent_cancelled(user_id: str, agent_id: str) -> bool:
    return _agent_key(user_id, agent_id) in _cancelled_agents


def request_cancel_workflow(user_id: str, run_id: str | None = None) -> None:
    _cancelled_workflows.add(_workflow_key(user_id, run_id))
    _cancelled_workflows.add(user_id)


def clear_workflow_cancel(user_id: str, run_id: str | None = None) -> None:
    _cancelled_workflows.discard(_workflow_key(user_id, run_id))
    _cancelled_workflows.discard(user_id)


def is_workflow_cancelled(user_id: str, run_id: str | None = None) -> bool:
    if user_id in _cancelled_workflows:
        return True
    if run_id and _workflow_key(user_id, run_id) in _cancelled_workflows:
        return True
    return False


def cancel_all_for_user(user_id: str, run_id: str | None = None) -> None:
    request_cancel_workflow(user_id, run_id)


def check_agent_cancelled(user_id: str, agent_id: str) -> None:
    if is_agent_cancelled(user_id, agent_id):
        raise AgentCancelledError(f"Agent {agent_id} was stopped")


def check_workflow_cancelled(user_id: str, run_id: str | None = None) -> None:
    if is_workflow_cancelled(user_id, run_id):
        raise AgentCancelledError("Workflow was stopped")
