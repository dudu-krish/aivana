"""Lightweight OpenAI-compatible chat completion helper."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

from app.config import settings


class LLMError(RuntimeError):
    pass


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
    payload = {
        "model": model or settings.planner_model,
        "temperature": settings.planner_temperature if temperature is None else temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    data = await asyncio.to_thread(_post_chat, payload)
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise LLMError("LLM returned non-object JSON")
    return parsed


def llm_configured() -> bool:
    return bool(settings.openai_api_key.strip())
