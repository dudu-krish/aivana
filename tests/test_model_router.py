from app.services.available_models import coerce_model, is_available_model
from app.services.model_router import pick_model, resolve_model, score_complexity


def test_short_simple_task_uses_economy_model():
    pick = pick_model(agent_id="spam-detection", text="Click here to win free money")
    assert pick.model_id in {"gpt-4.1-nano", "gpt-4o-mini"}
    assert is_available_model(pick.model_id)
    assert pick.score < 3.0


def test_large_input_planner_uses_stronger_model():
    text = "Customer escalation " * 400
    pick = pick_model(agent_id="planner", task="Analyze inbox and plan callbacks", text=text)
    assert pick.model_id in {"gpt-4o", "gpt-4.1"}
    assert is_available_model(pick.model_id)
    assert pick.score >= 5.0


def test_manual_unavailable_model_is_coerced():
    pick = resolve_model({"model": "gpt-5.2-pro", "model_mode": "manual"}, agent_id="planner", task="x")
    assert pick.model_id == "gpt-4o"
    assert "unavailable" in pick.reason.lower() or "mapped" in pick.reason.lower()


def test_auto_mode_routes_by_complexity():
    pick = resolve_model({"model": "auto"}, agent_id="root-cause-finder", text="debug payment timeout issue")
    assert pick.model_id in {"gpt-4.1-mini", "gpt-4o", "gpt-4.1"}
    assert is_available_model(pick.model_id)


def test_score_increases_with_input_length():
    low = score_complexity(agent_id="intent-detection", text="hello")
    high = score_complexity(agent_id="intent-detection", text="word " * 2000)
    assert high > low


def test_coerce_maps_fictional_slug():
    assert coerce_model("gpt-5.2-nano") == "gpt-4.1-nano"
