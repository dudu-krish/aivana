from app.services.available_models import fallback_chain
from app.services.llm import _is_model_not_found


def test_fallback_chain_starts_with_coerced_model():
    chain = fallback_chain("gpt-5.2-nano")
    assert chain[0] == "gpt-4.1-nano"
    assert "gpt-4o-mini" in chain


def test_model_not_found_detection():
    detail = '{"error":{"code":"model_not_found","message":"does not exist"}}'
    assert _is_model_not_found(detail) is True
