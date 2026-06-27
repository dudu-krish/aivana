"""OpenAI model IDs that are safe to call via the Chat Completions API."""

from __future__ import annotations

from app.config import settings

# Verified chat / JSON models on api.openai.com (avoid roadmap / preview slugs).
DEFAULT_AVAILABLE_CHAT_MODELS: tuple[str, ...] = (
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "gpt-4o-mini",
)

DEFAULT_AUDIO_MODELS: tuple[str, ...] = ("whisper-1",)

DEFAULT_IMAGE_MODELS: tuple[str, ...] = ("dall-e-3",)

# Map catalog / legacy slugs → nearest available chat model.
MODEL_ALIASES: dict[str, str] = {
    "gpt-5.5": "gpt-4.1",
    "gpt-5.5-pro": "gpt-4.1",
    "gpt-5.2": "gpt-4o",
    "gpt-5.2-pro": "gpt-4o",
    "gpt-5.2-mini": "gpt-4.1-mini",
    "gpt-5.2-nano": "gpt-4.1-nano",
    "gpt-5.1": "gpt-4.1",
    "gpt-5.1-thinking": "gpt-4.1",
    "gpt-5.1-pro": "gpt-4.1",
    "gpt-5": "gpt-4o",
    "gpt-5-mini": "gpt-4.1-mini",
    "gpt-5-nano": "gpt-4.1-nano",
    "gpt-oss-120b": "gpt-4.1",
    "gpt-oss-20b": "gpt-4.1-mini",
    "gpt-image-2": "dall-e-3",
    "gpt-image-1.5": "dall-e-3",
}

TIER_MODELS: dict[str, str] = {
    "frontier": "gpt-4.1",
    "strong": "gpt-4o",
    "balanced": "gpt-4.1-mini",
    "fast": "gpt-4.1-nano",
    "economy": "gpt-4o-mini",
}


def _parse_env_list(raw: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    items = [p.strip() for p in raw.split(",") if p.strip()]
    return tuple(items) if items else fallback


def available_chat_models() -> tuple[str, ...]:
    return _parse_env_list(getattr(settings, "llm_available_models", ""), DEFAULT_AVAILABLE_CHAT_MODELS)


def available_audio_models() -> tuple[str, ...]:
    return DEFAULT_AUDIO_MODELS


def available_image_models() -> tuple[str, ...]:
    return DEFAULT_IMAGE_MODELS


def is_available_model(model_id: str) -> bool:
    mid = str(model_id or "").strip()
    if not mid:
        return False
    if mid in available_chat_models():
        return True
    if mid in available_audio_models():
        return True
    if mid in available_image_models():
        return True
    return False


def coerce_model(model_id: str | None, *, default: str | None = None) -> str:
    """Return an API-safe model id, mapping unknown slugs to the nearest tier."""
    raw = str(model_id or "").strip()
    if not raw or raw.lower() == "auto":
        return default or settings.planner_model or "gpt-4o-mini"

    if raw in MODEL_ALIASES:
        return MODEL_ALIASES[raw]

    if is_available_model(raw):
        return raw

    lowered = raw.lower()
    if "whisper" in lowered or lowered.startswith("whisper"):
        return "whisper-1"
    if "dall-e" in lowered or "image" in lowered:
        return "dall-e-3"
    if "nano" in lowered or "mini" in lowered:
        return "gpt-4o-mini"
    if "4.1" in lowered:
        return "gpt-4.1"
    return default or "gpt-4o-mini"


def fallback_chain(model_id: str | None) -> list[str]:
    """Ordered candidates for LLM retries (deduped)."""
    primary = coerce_model(model_id)
    chain: list[str] = [primary]
    for candidate in (
        settings.planner_model,
        "gpt-4o-mini",
        "gpt-4.1-mini",
        "gpt-4o",
        "gpt-4.1",
    ):
        c = coerce_model(candidate)
        if c not in chain:
            chain.append(c)
    return chain
