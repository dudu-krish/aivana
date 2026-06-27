"""Tests for CreatorOS content operating system."""

import asyncio

import pytest

from app.agents.content_os import ContentDirectorAgent
from app.agents.content_registry import CONTENT_AGENTS, CONTENT_PIPELINE, is_content_agent
from app.agents.content_tools import (
    build_weekly_plan,
    rule_trend_research,
    run_content_agent,
    run_pipeline_sequential,
)
from app.services.tenant import TenantContext


@pytest.fixture
def base_state() -> dict:
    return {
        "creator_type": "Tech Entrepreneur",
        "niche": "AI Startups",
        "platforms": ["YouTube", "LinkedIn", "Twitter"],
        "goal": "Grow followers and leads",
    }


@pytest.fixture(autouse=True)
def _disable_llm_and_hitl(monkeypatch):
    """Keep CreatorOS tests fast and deterministic without live API calls."""
    monkeypatch.setattr("app.agents.content_tools.llm_configured", lambda: False)
    monkeypatch.setattr("app.agents.content_os.llm_configured", lambda: False)
    monkeypatch.setattr("app.config.settings.content_human_in_loop", False)


def test_registry_has_fifteen_agents() -> None:
    assert len(CONTENT_AGENTS) == 15
    assert len(CONTENT_PIPELINE) == 14


def test_normalize_assam_goal() -> None:
    from app.agents.content_tools import normalize_creator_context

    state = normalize_creator_context({
        "goal": "Increase views and audience from Assam",
        "niche": "",
        "creator_type": "Tech Entrepreneur",
    })
    assert "assam" in state["niche"].lower() or "assam" in state.get("region", "").lower()


def test_is_content_agent() -> None:
    assert is_content_agent("content-director")
    assert is_content_agent("content-trend-research")
    assert not is_content_agent("planner")


def test_trend_research_rule_output(base_state: dict) -> None:
    from app.agents.content_tools import normalize_creator_context

    state = normalize_creator_context({**base_state, "goal": "Grow audience from Assam", "niche": "Assam"})
    out = rule_trend_research(state)
    assert out["topics"]
    assert any("assam" in t["title"].lower() for t in out["topics"])


def test_run_content_agent_rules(base_state: dict) -> None:
    out = asyncio.run(run_content_agent("content-hook-generator", {
        **base_state,
        "pipeline_results": {"content-strategy": {"primary_topic": "AI Agents"}},
    }))
    assert out["mode"] == "rules"
    assert out["result"]["hooks"]


def test_pipeline_sequential_while_loop(base_state: dict) -> None:
    final = asyncio.run(run_pipeline_sequential(base_state))
    assert len(final["assigned_agents"]) == len(CONTENT_PIPELINE)
    assert final["weekly_plan"]
    assert all(agent_id in final["pipeline_results"] for agent_id in CONTENT_PIPELINE)


def test_build_weekly_plan(base_state: dict) -> None:
    pipeline = {
        "content-strategy": {
            "calendar": [{"day": "Day 1", "focus": "AI Agents", "platforms": ["YouTube"]}],
        },
        "content-hook-generator": {"hooks": [{"text": "Hook one"}]},
        "content-publishing": {"schedule": [{"slot": "2026-06-23T09:00:00Z"}]},
    }
    plan = build_weekly_plan({**base_state, "pipeline_results": pipeline})
    assert plan[0]["hook"] == "Hook one"


def test_content_director_rule_pipeline() -> None:
    tenant = TenantContext(user_id="test-user", email="test@example.com", name="Test")
    director = ContentDirectorAgent(tenant)
    result = asyncio.run(director.run(
        creator_type="Tech Entrepreneur",
        niche="AI Startups",
        platforms=["YouTube", "LinkedIn"],
        goal="Grow followers",
    ))
    assert result["status"] == "completed"
    assert result["weekly_plan"]
    assert len(result["assigned_agents"]) >= len(CONTENT_PIPELINE)
    assert "content-trend-research" in result["pipeline_results"]
