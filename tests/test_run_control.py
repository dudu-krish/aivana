from app.services.run_control import (
    AgentCancelledError,
    cancel_all_for_user,
    check_agent_cancelled,
    clear_agent_cancel,
    clear_workflow_cancel,
    is_agent_cancelled,
    is_workflow_cancelled,
    request_cancel_agent,
    request_cancel_workflow,
)


def test_agent_cancel_roundtrip() -> None:
    clear_agent_cancel("user-1", "planner")
    assert not is_agent_cancelled("user-1", "planner")
    request_cancel_agent("user-1", "planner")
    assert is_agent_cancelled("user-1", "planner")
    raised = False
    try:
        check_agent_cancelled("user-1", "planner")
    except AgentCancelledError:
        raised = True
    assert raised
    other_raised = False
    try:
        check_agent_cancelled("user-2", "planner")
    except AgentCancelledError:
        other_raised = True
    assert not other_raised
    clear_agent_cancel("user-1", "planner")
    assert not is_agent_cancelled("user-1", "planner")


def test_workflow_cancel_by_run_id() -> None:
    clear_workflow_cancel("user-1", "run-abc")
    request_cancel_workflow("user-1", "run-abc")
    assert is_workflow_cancelled("user-1", "run-abc")
    assert is_workflow_cancelled("user-1", "run-other")
    clear_workflow_cancel("user-1", "run-abc")
    assert not is_workflow_cancelled("user-1", "run-abc")


def test_cancel_all_for_user() -> None:
    clear_workflow_cancel("user-9")
    cancel_all_for_user("user-9", "run-1")
    assert is_workflow_cancelled("user-9", "run-1")
    clear_workflow_cancel("user-9", "run-1")
