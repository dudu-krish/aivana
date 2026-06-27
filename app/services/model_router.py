"""Pick an LLM based on agent role, input size, and task complexity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.available_models import TIER_MODELS, coerce_model, is_available_model

COMPLEX_KEYWORDS = (
    "architect",
    "architecture",
    "design review",
    "research",
    "strategy",
    "multi-step",
    "analyze",
    "investigate",
    "root cause",
    "debug",
    "complex",
    "critical",
    "mission",
    "planning",
    "code review",
    "reasoning",
    "compliance",
    "legal",
)

SIMPLE_KEYWORDS = (
    "classify",
    "tag",
    "label",
    "extract",
    "parse",
    "summarize",
    "simple",
    "quick",
    "short",
    "yes/no",
    "categorize",
    "keyword",
    "spam",
    "duplicate",
)

HEAVY_AGENTS = frozenset(
    {
        "planner",
        "root-cause-finder",
        "org-knowledge-base",
        "chat-agent",
        "summarizer",
    }
)

MEDIUM_AGENTS = frozenset(
    {
        "intent-detection",
        "sentiment-analysis",
        "entity-extraction",
        "topic-modeling",
        "topic-detection",
        "risk-detection",
        "similarity-detection",
        "read-pdf",
        "web-search",
    }
)

LIGHT_AGENTS = frozenset(
    {
        "spam-detection",
        "keyword-extraction",
        "urgency-detection",
    }
)


@dataclass(frozen=True)
class ModelPick:
    model_id: str
    tier: str
    score: float
    reason: str


def _combined_text(*parts: Any) -> str:
    chunks: list[str] = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        if text:
            chunks.append(text)
    return " ".join(chunks)


def score_complexity(
    *,
    agent_id: str = "",
    text: str = "",
    task: str = "",
    prompt: str = "",
    question: str = "",
    connected_agents: list[str] | None = None,
    action: str = "",
    source_size: int = 0,
) -> float:
    blob = _combined_text(text, task, prompt, question)
    blob_lower = blob.lower()
    char_len = max(len(blob), source_size)

    score = 0.0

    if char_len > 12000:
        score += 4.0
    elif char_len > 4000:
        score += 3.0
    elif char_len > 1500:
        score += 2.0
    elif char_len > 400:
        score += 1.0

    for kw in COMPLEX_KEYWORDS:
        if kw in blob_lower:
            score += 1.2

    for kw in SIMPLE_KEYWORDS:
        if kw in blob_lower:
            score -= 0.7

    aid = (agent_id or "").strip().lower()
    if aid in HEAVY_AGENTS:
        score += 2.5
    elif aid in MEDIUM_AGENTS:
        score += 1.0
    elif aid in LIGHT_AGENTS:
        score -= 0.5

    connected = connected_agents or []
    if len(connected) > 4:
        score += 1.5
    elif len(connected) > 2:
        score += 0.5

    if (action or "").lower() == "ask" and char_len > 200:
        score += 1.0

    if re.search(r"\b(?:api|sql|python|typescript|javascript|refactor)\b", blob_lower):
        score += 1.0

    return max(0.0, score)


def pick_model(
    *,
    agent_id: str = "",
    text: str = "",
    task: str = "",
    prompt: str = "",
    question: str = "",
    connected_agents: list[str] | None = None,
    action: str = "",
    source_size: int = 0,
) -> ModelPick:
    blob_lower = _combined_text(text, task, prompt, question).lower()
    aid = (agent_id or "").strip().lower()

    if aid in {"speech-agent"} or "transcrib" in blob_lower or "whisper" in blob_lower:
        return ModelPick("whisper-1", "speech", 0.0, "Speech / audio transcription task")

    if "generate image" in blob_lower or "image generation" in blob_lower:
        return ModelPick("dall-e-3", "image", 0.0, "Image generation task")

    score = score_complexity(
        agent_id=agent_id,
        text=text,
        task=task,
        prompt=prompt,
        question=question,
        connected_agents=connected_agents,
        action=action,
        source_size=source_size,
    )

    if score >= 7.0:
        tier = "frontier"
        reason = "High complexity — large input, deep reasoning, or critical planning"
    elif score >= 5.0:
        tier = "strong"
        reason = "Moderate-high complexity — multi-step analysis or rich context"
    elif score >= 3.0:
        tier = "balanced"
        reason = "Balanced workload — standard NLP / workflow step"
    elif score >= 1.5:
        tier = "fast"
        reason = "Light task — classification, tagging, or short input"
    else:
        tier = "economy"
        reason = "Minimal complexity — quick pass over small input"

    model_id = TIER_MODELS[tier]
    return ModelPick(model_id, tier, score, reason)


def is_auto_model(model: str | None) -> bool:
    value = str(model or "").strip().lower()
    return not value or value == "auto"


def resolve_model(agent_config: dict[str, Any] | None, **context: Any) -> ModelPick:
    cfg = agent_config or {}
    explicit = str(cfg.get("model") or "").strip()
    mode = str(cfg.get("model_mode") or "auto").strip().lower()

    if explicit and explicit.lower() != "auto" and mode != "auto":
        coerced = coerce_model(explicit)
        if coerced == explicit and is_available_model(explicit):
            return ModelPick(coerced, "manual", 0.0, "Manual model selection")
        return ModelPick(
            coerced,
            "manual",
            0.0,
            f"Using {coerced} (mapped from unavailable {explicit})",
        )

    pick = pick_model(
        agent_id=str(context.get("agent_id") or cfg.get("agent_id") or ""),
        text=str(context.get("text") or ""),
        task=str(context.get("task") or ""),
        prompt=str(context.get("prompt") or cfg.get("prompt") or ""),
        question=str(context.get("question") or ""),
        connected_agents=context.get("connected_agents"),
        action=str(context.get("action") or ""),
        source_size=int(context.get("source_size") or 0),
    )
    return ModelPick(coerce_model(pick.model_id), pick.tier, pick.score, pick.reason)


def apply_model_routing(agent_config: dict[str, Any] | None, **context: Any) -> dict[str, Any]:
    cfg = dict(agent_config or {})
    pick = resolve_model(cfg, **context)
    cfg["model"] = pick.model_id
    cfg["_model_pick_reason"] = pick.reason
    cfg["_model_pick_tier"] = pick.tier
    return cfg
