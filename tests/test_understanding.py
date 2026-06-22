"""Tests for Understanding micro-agents."""

from app.agents.understanding import _rule_analyze
from app.agents.understanding_registry import UNDERSTANDING_AGENTS, is_understanding_agent


def test_registry_has_twenty_agents() -> None:
    assert len(UNDERSTANDING_AGENTS) == 20


def test_is_understanding_agent() -> None:
    assert is_understanding_agent("intent-detection")
    assert not is_understanding_agent("planner")


def test_sentiment_rule_analyze() -> None:
    out = _rule_analyze("sentiment-detection", "Thanks for the great support!", "")
    assert out["result"]["sentiment"] == "positive"


def test_duplicate_detection_requires_reference() -> None:
    out = _rule_analyze("duplicate-detection", "hello world", "")
    assert out.get("status") == "error"
