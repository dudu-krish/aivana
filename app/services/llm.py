"""Lightweight OpenAI-compatible chat completion helper."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

from app.config import settings
from app.services.available_models import coerce_model, fallback_chain


class LLMError(RuntimeError):
    pass


def _is_model_not_found(detail: str) -> bool:
    lowered = detail.lower()
    return "model_not_found" in lowered or "does not exist" in lowered


def _post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = settings.openai_api_key.strip()
    if not api_key:
        raise LLMError("OPENAI_API_KEY is not configured")

    base = settings.openai_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=settings.llm_timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise LLMError(f"LLM request failed ({exc.code}): {detail}") from exc


async def complete_json(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    requested = model or settings.planner_model
    candidates = fallback_chain(requested)
    last_error: LLMError | None = None

    for candidate in candidates:
        payload = {
            "model": coerce_model(candidate),
            "temperature": settings.planner_temperature if temperature is None else temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            data = await asyncio.to_thread(_post_chat, payload)
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise LLMError("LLM returned non-object JSON")
            return parsed
        except LLMError as exc:
            last_error = exc
            if _is_model_not_found(str(exc)):
                continue
            raise

    raise last_error or LLMError(f"No available model for request (tried: {', '.join(candidates)})")


async def complete_with_tools(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str | None = None,
    temperature: float | None = None,
    tool_choice: str | dict[str, Any] | None = "auto",
) -> dict[str, Any]:
    """Chat completion with tool calling — returns the assistant message dict."""
    requested = model or settings.planner_model
    candidates = fallback_chain(requested)
    last_error: LLMError | None = None

    for candidate in candidates:
        payload: dict[str, Any] = {
            "model": coerce_model(candidate),
            "temperature": settings.planner_temperature if temperature is None else temperature,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice or "auto",
        }
        try:
            data = await asyncio.to_thread(_post_chat, payload)
            choice = data["choices"][0]
            return {
                "message": choice["message"],
                "finish_reason": choice.get("finish_reason"),
                "model": candidate,
            }
        except LLMError as exc:
            last_error = exc
            if _is_model_not_found(str(exc)):
                continue
            raise

    raise last_error or LLMError(f"No available model for tool request (tried: {', '.join(candidates)})")


def llm_configured() -> bool:
    return bool(settings.openai_api_key.strip())
