"""LangChain integration — chat models and optional structured output."""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.services.available_models import coerce_model, fallback_chain

_LANGCHAIN_AVAILABLE: bool | None = None


def langchain_available() -> bool:
    global _LANGCHAIN_AVAILABLE
    if _LANGCHAIN_AVAILABLE is None:
        try:
            import langchain_openai  # noqa: F401
            import langgraph  # noqa: F401

            _LANGCHAIN_AVAILABLE = True
        except ImportError:
            _LANGCHAIN_AVAILABLE = False
    return _LANGCHAIN_AVAILABLE


def get_chat_model(model: str | None = None, temperature: float | None = None):
    if not langchain_available():
        raise RuntimeError("LangChain is not installed")
    if not settings.openai_api_key.strip():
        raise RuntimeError("OPENAI_API_KEY is not configured")

    from langchain_openai import ChatOpenAI

    requested = model or settings.planner_model
    resolved = coerce_model(fallback_chain(requested)[0])
    return ChatOpenAI(
        model=resolved,
        temperature=settings.planner_temperature if temperature is None else temperature,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.llm_timeout_seconds,
    )


async def invoke_json(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_chat_model(model, temperature)
    structured = llm.with_structured_output(method="json_mode")
    raw = await structured.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    return {"result": raw}
