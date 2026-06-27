"""CreatorOS tool executors — rule fallbacks, LLM-backed specialists, and human-in-the-loop."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.agents.content_registry import CONTENT_AGENTS, CONTENT_PIPELINE, agent_name
from app.config import settings
from app.services.llm import LLMError, complete_json, llm_configured

# Production agents that pause for human questions + output review
HITL_AGENT_IDS: frozenset[str] = frozenset({
    "content-hook-generator",
    "content-script-writer",
    "content-visual-planner",
    "content-thumbnail",
    "content-video-creator",
})

HITL_QUESTIONS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "content-hook-generator": {
        "input": [
            {"id": "audience", "label": "Who is your primary audience?", "type": "text",
             "placeholder": "Assamese youth, local entrepreneurs, diaspora…"},
            {"id": "tone", "label": "Hook tone", "type": "select",
             "options": ["Inspiring", "Educational", "Entertainment", "Contrarian", "Local pride"]},
            {"id": "language", "label": "Language for hooks", "type": "select",
             "options": ["Assamese", "English", "Hindi", "Mixed Assamese + English"]},
        ],
        "review": [
            {"id": "decision", "label": "Approve these hooks?", "type": "select",
             "options": ["Approve", "Revise — add notes below", "Regenerate"]},
            {"id": "notes", "label": "Edits or direction (optional)", "type": "textarea", "optional": True},
        ],
    },
    "content-script-writer": {
        "input": [
            {"id": "format", "label": "Primary video format", "type": "select",
             "options": ["YouTube long-form", "YouTube Shorts", "LinkedIn video", "Multi-platform"]},
            {"id": "length", "label": "Target length", "type": "select",
             "options": ["30–60 sec intro", "3–5 min", "8–12 min", "Thread / carousel"]},
            {"id": "cta", "label": "Call to action", "type": "text",
             "placeholder": "Subscribe, visit website, join community…"},
        ],
        "review": [
            {"id": "decision", "label": "Approve script draft?", "type": "select",
             "options": ["Approve", "Revise — add notes below", "Regenerate"]},
            {"id": "notes", "label": "Script edits (optional)", "type": "textarea", "optional": True},
        ],
    },
    "content-visual-planner": {
        "input": [
            {"id": "location", "label": "Filming location / setting", "type": "text",
             "placeholder": "Guwahati studio, tea garden, Brahmaputra ghats…"},
            {"id": "style", "label": "Visual style", "type": "select",
             "options": ["Documentary", "Vlog", "Cinematic B-roll", "Talking head + graphics"]},
            {"id": "gear", "label": "Available gear (optional)", "type": "text",
             "placeholder": "Phone only, DSLR, drone…"},
        ],
        "review": [
            {"id": "decision", "label": "Approve shot list?", "type": "select",
             "options": ["Approve", "Revise — add notes below", "Regenerate"]},
            {"id": "notes", "label": "Shot changes (optional)", "type": "textarea", "optional": True},
        ],
    },
    "content-thumbnail": {
        "input": [
            {"id": "emotion", "label": "Thumbnail emotion", "type": "select",
             "options": ["Surprise", "Curiosity", "Urgency", "Joy", "Local pride"]},
            {"id": "text_overlay", "label": "Text on thumbnail?", "type": "select",
             "options": ["Short bold text (3–5 words)", "No text — face only", "Assamese text"]},
            {"id": "face", "label": "Include creator face?", "type": "select",
             "options": ["Yes — close-up", "No — scenery/graphic only"]},
        ],
        "review": [
            {"id": "decision", "label": "Approve thumbnail concepts?", "type": "select",
             "options": ["Approve", "Revise — add notes below", "Regenerate"]},
            {"id": "notes", "label": "Thumbnail feedback (optional)", "type": "textarea", "optional": True},
        ],
    },
    "content-video-creator": {
        "input": [
            {"id": "intro_style", "label": "Intro video style", "type": "select",
             "options": ["Cinematic documentary", "Energetic vlog", "Cultural showcase", "Minimal modern"]},
            {"id": "language", "label": "Voiceover / on-screen language", "type": "select",
             "options": ["Assamese", "English", "Assamese with English subtitles", "No dialogue — music only"]},
            {"id": "landmarks", "label": "Local visuals to feature", "type": "text",
             "placeholder": "Brahmaputra, Kaziranga, tea gardens, Bihu dance…"},
        ],
        "review": [
            {"id": "decision", "label": "Generate video with this Veo prompt?", "type": "select",
             "options": ["Generate video", "Edit prompt below first", "Skip video generation"]},
            {"id": "prompt_override", "label": "Custom Veo prompt (optional)", "type": "textarea", "optional": True},
        ],
    },
}


def _goal(state: dict[str, Any]) -> str:
    return str(state.get("goal") or "Grow audience and leads").strip()


def _detect_region_from_text(goal: str, niche: str) -> str:
    text = f"{goal} {niche}".lower()
    if "assam" in text or "assamese" in text or "guwahati" in text:
        return "Assam, Northeast India"
    if "northeast" in text:
        return "Northeast India"
    return ""


def normalize_creator_context(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure niche, region, and audience align with the user's stated goal."""
    goal = _goal(state)
    niche = str(state.get("niche") or "").strip()
    creator = str(state.get("creator_type") or "").strip()

    generic_niches = {"", "ai startups", "tech entrepreneur", "creator", "creators"}
    if niche.lower() in generic_niches:
        if re.search(r"\bassam\b|\bassamese\b", goal, re.I):
            niche = "Assam audience growth & regional creator economy"
        elif goal:
            niche = goal[:160]

    if creator.lower() in {"", "tech entrepreneur"} and re.search(r"\bassam\b", goal, re.I):
        creator = "Regional Content Creator (Assam)"

    region = _detect_region_from_text(goal, niche)
    return {
        **state,
        "goal": goal,
        "niche": niche or goal[:120] or "Content creators",
        "creator_type": creator or "Content Creator",
        "region": region,
        "audience_focus": region or niche,
    }


def _niche_label(state: dict[str, Any]) -> str:
    return str(state.get("niche") or state.get("creator_type") or "creators").strip()


def _region_label(state: dict[str, Any]) -> str:
    return str(state.get("region") or state.get("audience_focus") or _niche_label(state)).strip()


def _platforms(state: dict[str, Any]) -> list[str]:
    raw = state.get("platforms") or ["YouTube", "LinkedIn", "Twitter"]
    return [str(p).strip() for p in raw if str(p).strip()]


def _prior(state: dict[str, Any], agent_id: str) -> dict[str, Any]:
    return dict(state.get("pipeline_results", {}).get(agent_id) or {})


def _human_answers(state: dict[str, Any], agent_id: str) -> dict[str, Any]:
    return dict(state.get("human_answers", {}).get(agent_id, {}))


def _item_text(item: Any, *keys: str) -> str:
    """Extract display text from rule/LLM output items (dict or plain string)."""
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in keys:
            val = item.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        for val in item.values():
            if isinstance(val, str) and val.strip():
                return val.strip()
    return str(item).strip() if item else ""


def _coerce_text_list(items: Any) -> list[Any]:
    """Normalize LLM/rule outputs that may be a list, a string, or a nested dict."""
    if items is None:
        return []
    if isinstance(items, str):
        return [items] if items.strip() else []
    if isinstance(items, dict):
        for key in ("hooks", "scripts", "shot_list", "items", "result", "text", "body"):
            inner = items.get(key)
            if inner is not None:
                return _coerce_text_list(inner)
        return [items]
    if isinstance(items, list):
        return items
    return [items]


def _first_item_text(items: Any, *keys: str, default: str = "") -> str:
    coerced = _coerce_text_list(items)
    if not coerced:
        return default
    text = _item_text(coerced[0], *keys)
    return text or default

def rule_trend_research(state: dict[str, Any]) -> dict[str, Any]:
    niche = _niche_label(state)
    region = _region_label(state)
    loc = region or niche
    topics = [
        {"title": f"Hidden gems in {loc} tourists never see", "score": 91, "source": "YouTube"},
        {"title": f"How creators from {loc} are going viral in 2026", "score": 89, "source": "YouTube"},
        {"title": f"Local culture stories that win on Shorts — {loc}", "score": 86, "source": "X"},
        {"title": f"Assamese creators crossing 1M views — what changed?", "score": 84, "source": "Reddit"},
        {"title": f"Google Trends: rising searches in {loc}", "score": 78, "source": "Google Trends"},
    ]
    if "assam" not in loc.lower():
        topics = [
            {"title": f"Viral topics in {niche} this week", "score": 92, "source": "YouTube"},
            {"title": f"Audience growth playbook for {niche}", "score": 88, "source": "LinkedIn"},
            {"title": f"Short-form vs long-form in {niche}", "score": 85, "source": "X"},
        ]
    return {"topics": topics, "competitor_content": [t["title"] for t in topics[:3]], "region": loc}


def rule_audience_psychology(state: dict[str, Any]) -> dict[str, Any]:
    niche = _niche_label(state)
    region = _region_label(state)
    return {
        "pain_points": [
            f"Hard to reach viewers outside {region or niche}",
            "Limited monetization for regional language content",
            "Algorithm favors Hindi/English — Assamese creators feel invisible",
        ] if "assam" in f"{region} {niche}".lower() else [
            "Inconsistent posting",
            f"Hard to stand out in {niche}",
            "No clear content strategy",
        ],
        "desires": [
            "Grow views and subscribers from home state",
            "Pride in showcasing local culture globally",
            "Sustainable income from content",
        ] if "assam" in f"{region} {niche}".lower() else [
            "Predictable audience growth",
            "Authority in their niche",
            "Content that converts",
        ],
        "objections": ["Worried regional content won't scale", "Not enough time to edit"],
        "curiosity_gaps": [
            f"What content formats work best for {region or niche} audiences?",
            "How do top regional creators batch content?",
        ],
    }


def rule_content_strategy(state: dict[str, Any]) -> dict[str, Any]:
    platforms = _platforms(state)
    trends = _prior(state, "content-trend-research").get("topics") or []
    top_topic = trends[0]["title"] if trends else f"Growing audience in {_region_label(state)}"
    goal = _goal(state)
    calendar = []
    for day in range(1, 8):
        calendar.append({
            "day": f"Day {day}",
            "focus": top_topic if day <= 3 else f"Community engagement — {goal[:60]}",
            "platforms": platforms[: min(len(platforms), 2)],
        })
    return {
        "youtube": 3, "linkedin": 4, "twitter": 10, "instagram": 7,
        "calendar": calendar,
        "funnel_strategy": f"Local pride Shorts → Authority long-form → Goal: {goal[:80]}",
        "primary_topic": top_topic,
        "region": _region_label(state),
    }


def rule_hook_generator(state: dict[str, Any]) -> dict[str, Any]:
    topic = _prior(state, "content-strategy").get("primary_topic") or _goal(state)
    region = _region_label(state)
    human = _human_answers(state, "content-hook-generator")
    lang = human.get("language") or ("Assamese" if "assam" in region.lower() else "English")
    return {
        "hooks": [
            {"type": "video_open", "text": f"Nobody is telling {region} creators this secret to 10x views.", "topic": topic, "language": lang},
            {"type": "video_open", "text": f"I grew my audience from {region} with zero ad spend. Here's how.", "topic": topic, "language": lang},
            {"type": "youtube_short", "text": f"POV: You finally crack the algorithm in {region} 🇮🇳", "topic": topic, "language": lang},
            {"type": "linkedin_headline", "text": f"The {topic[:40]} playbook for regional creators", "topic": topic, "language": lang},
        ],
        "human_input": human,
    }


def rule_script_writer(state: dict[str, Any]) -> dict[str, Any]:
    hooks = _prior(state, "content-hook-generator").get("hooks") or []
    opener = _first_item_text(
        hooks, "text", "hook", "title",
        default=f"Growing your audience in {_region_label(state)} starts here.",
    )
    topic = _prior(state, "content-strategy").get("primary_topic") or _goal(state)
    human = _human_answers(state, "content-script-writer")
    cta = human.get("cta") or "Subscribe and comment your city — I'll shout you out!"
    return {
        "scripts": [
            {
                "format": "youtube_long",
                "framework": "Hook → Story → Value → CTA",
                "title": topic,
                "body": f"{opener}\n\nStory: authentic journey from {_region_label(state)}.\nValue: 3 tactics tied to goal: {_goal(state)}.\nCTA: {cta}",
            },
            {
                "format": "youtube_short",
                "framework": "Hook → Punchline",
                "body": f"{opener}\n\nQuick tip #1 for Assamese creators.\n{cta}",
            },
            {
                "format": "linkedin_post",
                "framework": "PAS",
                "body": f"Problem: invisible in the algorithm.\nAgitate: Hindi/English dominate feeds.\nSolution: {topic}. {cta}",
            },
        ],
        "human_input": human,
    }


def rule_visual_planner(state: dict[str, Any]) -> dict[str, Any]:
    human = _human_answers(state, "content-visual-planner")
    location = human.get("location") or _region_label(state) or "Local outdoor B-roll"
    return {
        "shot_list": [
            {"scene": 1, "type": "talking_head", "notes": f"Hook delivery — {location}, golden hour"},
            {"scene": 2, "type": "b_roll", "notes": f"Aerial/drone of {location} — river, markets, culture"},
            {"scene": 3, "type": "talking_head", "notes": "Mid-video value — screen + face split"},
            {"scene": 4, "type": "b_roll", "notes": "Community faces, local food, festivals"},
            {"scene": 5, "type": "talking_head", "notes": "CTA — direct to camera, high energy"},
        ],
        "human_input": human,
    }


def rule_thumbnail(state: dict[str, Any]) -> dict[str, Any]:
    topic = _prior(state, "content-strategy").get("primary_topic") or _goal(state)
    region = _region_label(state)
    human = _human_answers(state, "content-thumbnail")
    emotion = human.get("emotion") or "Local pride"
    return {
        "thumbnails": [
            {"text": f"{region} Creators: Read This", "emotion": emotion, "ctr_prediction": 13.2},
            {"text": topic[:28], "emotion": "curiosity", "ctr_prediction": 11.0},
            {"text": "Views 10x 🚀", "emotion": "surprise", "ctr_prediction": 10.5},
        ],
        "human_input": human,
    }


async def rule_video_creator(state: dict[str, Any]) -> dict[str, Any]:
    """Generate intro video via Veo (call after human approves prompt)."""
    from app.services.veo_video import VeoError, build_intro_veo_prompt, generate_veo_video, veo_configured

    human = _human_answers(state, "content-video-creator")
    prompt = _build_veo_prompt(state, human)
    decision = str(human.get("decision") or "").lower()
    if "skip" in decision:
        return {
            "status": "skipped",
            "veo_prompt": prompt,
            "message": "Video generation skipped by user",
            "human_input": human,
        }

    user_id = str(state.get("_user_id") or "anonymous")
    out_dir = settings.data_dir / "generated_videos" / user_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"intro_{len(list(out_dir.glob('*.mp4')))}.mp4"

    if not veo_configured():
        return {
            "status": "simulated",
            "veo_prompt": prompt,
            "message": "Set GEMINI_API_KEY in .env to generate real Veo videos",
            "human_input": human,
        }

    agent_id = "content-video-creator"
    try:
        await _emit_agent_progress(
            user_id,
            agent_id,
            "Generating intro video with Gemini Veo — this usually takes 2–10 minutes…",
        )
        video = await generate_veo_video(
            prompt,
            output_path=out_path,
            duration_seconds=settings.veo_duration_seconds,
            aspect_ratio=settings.veo_aspect_ratio,
        )
        await _emit_agent_progress(user_id, agent_id, "Intro video generated successfully")
        return {
            "status": "generated",
            "intro_video": video.get("local_path"),
            "video_uri": video.get("video_uri"),
            "veo_prompt": prompt,
            "human_input": human,
        }
    except VeoError as exc:
        return {
            "status": "error",
            "veo_prompt": prompt,
            "error": str(exc),
            "human_input": human,
        }


def _build_veo_prompt(state: dict[str, Any], human: dict[str, Any]) -> str:
    from app.services.veo_video import build_intro_veo_prompt

    hooks = _coerce_text_list(_prior(state, "content-hook-generator").get("hooks"))
    scripts = _coerce_text_list(_prior(state, "content-script-writer").get("scripts"))
    visuals = _coerce_text_list(_prior(state, "content-visual-planner").get("shot_list"))
    hook = _first_item_text(hooks, "text", "hook", "title")
    script_excerpt = _first_item_text(scripts, "body", "script", "text")[:400]
    visual_notes = "; ".join(
        _item_text(s, "notes", "description", "text")
        for s in _coerce_text_list(visuals)[:3]
    )
    prompt = build_intro_veo_prompt(
        niche=_niche_label(state),
        goal=_goal(state),
        region=_region_label(state),
        hook=hook,
        script_excerpt=script_excerpt,
        visual_notes=visual_notes,
        human_answers=human,
    )
    if human.get("prompt_override", "").strip():
        prompt = human["prompt_override"].strip()
    return prompt


def draft_video_creator(state: dict[str, Any]) -> dict[str, Any]:
    human = _human_answers(state, "content-video-creator")
    prompt = _build_veo_prompt(state, human)
    return {
        "status": "awaiting_video_generation",
        "veo_prompt": prompt,
        "message": "Review the Veo prompt below, then approve to generate the intro video.",
        "human_input": human,
    }


def rule_video_editing(state: dict[str, Any]) -> dict[str, Any]:
    shots = _prior(state, "content-visual-planner").get("shot_list") or []
    intro = _prior(state, "content-video-creator")
    return {
        "edit_plan": {
            "cuts": ["Remove silence > 0.4s", "Jump cuts every 3–5s on talking head"],
            "captions": "Bold keyword highlights — Assamese + English if mixed",
            "effects": ["Punch-in zoom on hook", "Ken Burns on B-roll"],
            "b_roll_suggestions": [
                _item_text(s, "notes", "description", "text")
                for s in shots
                if isinstance(s, (dict, str)) and (not isinstance(s, dict) or s.get("type") == "b_roll")
            ],
            "intro_clip": intro.get("intro_video") or intro.get("veo_prompt"),
            "tools": ["CapCut", "Descript", "Premiere"],
        }
    }


def rule_caption_hashtag(state: dict[str, Any]) -> dict[str, Any]:
    topic = _prior(state, "content-strategy").get("primary_topic") or _goal(state)
    region = _region_label(state)
    tags = ["#Assam", "#Assamese", "#NortheastIndia", "#CreatorEconomy", "#YouTube"]
    if "assam" not in region.lower():
        tags = ["#ContentStrategy", "#CreatorEconomy", "#YouTube", "#Growth"]
    return {
        "captions": {
            "youtube_description": f"{topic}\n\nGoal: {_goal(state)}\n\n{' '.join(tags)}",
            "linkedin": f"{topic} — built for {region} audiences.",
            "twitter": f"Thread: growing views in {region} 🧵",
            "instagram": f"POV: {region} creator energy ✨",
        },
        "hashtags": tags,
    }


def rule_publishing(state: dict[str, Any]) -> dict[str, Any]:
    platforms = _platforms(state)
    schedule = []
    for i, platform in enumerate(platforms):
        schedule.append({
            "platform": platform,
            "slot": f"2026-06-{23 + i:02d}T09:00:00Z",
            "status": "scheduled",
        })
    return {"schedule": schedule, "integrations": platforms}


def rule_community(state: dict[str, Any]) -> dict[str, Any]:
    region = _region_label(state)
    return {
        "replies": [
            {"channel": "comment", "question": "How do I grow from Assam?",
             "reply": f"Start with Shorts in your language, post 3x/week, engage {region} hashtags."},
            {"channel": "dm", "question": "Can you review my channel?",
             "reply": "Share your niche and last 3 videos — I'll suggest hooks and topics."},
        ]
    }


def rule_analytics(state: dict[str, Any]) -> dict[str, Any]:
    topic = _prior(state, "content-strategy").get("primary_topic") or _goal(state)
    return {
        "best_topic": topic,
        "region": _region_label(state),
        "ctr": 12.5,
        "watch_time_avg_minutes": 4.2,
        "engagement_rate": 6.8,
        "followers_gained": 1240,
        "leads": 38,
    }


def rule_learning(state: dict[str, Any]) -> dict[str, Any]:
    analytics = _prior(state, "content-analytics")
    hooks = _prior(state, "content-hook-generator").get("hooks") or []
    return {
        "learnings": [
            {"insight": f"Regional pride hooks outperformed generic titles for {_region_label(state)}", "confidence": 0.85},
            {"insight": "Shorts drove 70% of new subscribers", "confidence": 0.78},
        ],
        "best_hook": _first_item_text(hooks, "text", "hook", "title") or None,
        "knowledge_base_updates": [
            f"Creator goal: {_goal(state)}",
            f"Primary audience: {_region_label(state)}",
        ],
    }


RULE_EXECUTORS: dict[str, Any] = {
    "content-trend-research": rule_trend_research,
    "content-audience-psychology": rule_audience_psychology,
    "content-strategy": rule_content_strategy,
    "content-hook-generator": rule_hook_generator,
    "content-script-writer": rule_script_writer,
    "content-visual-planner": rule_visual_planner,
    "content-thumbnail": rule_thumbnail,
    "content-video-creator": rule_video_creator,
    "content-video-editing": rule_video_editing,
    "content-caption-hashtag": rule_caption_hashtag,
    "content-publishing": rule_publishing,
    "content-community": rule_community,
    "content-analytics": rule_analytics,
    "content-learning": rule_learning,
}


async def _emit_agent_progress(
    user_id: str | None,
    agent_id: str,
    message: str,
    *,
    data: dict[str, Any] | None = None,
) -> None:
    if not user_id:
        return
    from app.services.event_bus import event_bus

    await event_bus.emit(
        user_id,
        agent_id,
        agent_name(agent_id),
        "progress",
        message,
        data or {},
    )


async def _emit_output_preview(user_id: str | None, agent_id: str, result: dict[str, Any]) -> None:
    if not user_id:
        return
    from app.services.event_bus import event_bus

    await event_bus.emit(
        user_id,
        agent_id,
        agent_name(agent_id),
        "agent_output",
        f"{agent_name(agent_id)} draft ready — review below",
        {"result": result, "agent_id": agent_id},
    )


async def _run_hitl(
    agent_id: str,
    state: dict[str, Any],
    *,
    user_id: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    from app.services.human_input import request_human_input

    cfg = HITL_QUESTIONS.get(agent_id, {})
    name = agent_name(agent_id)

    input_answers = await request_human_input(
        user_id or "anonymous",
        agent_id,
        name,
        phase="input",
        questions=cfg.get("input") or [],
        run_id=run_id,
    )
    state.setdefault("human_answers", {})[agent_id] = {**state.get("human_answers", {}).get(agent_id, {}), **input_answers}
    return input_answers


async def _review_hitl(
    agent_id: str,
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    user_id: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    from app.services.human_input import request_human_input

    cfg = HITL_QUESTIONS.get(agent_id, {})
    name = agent_name(agent_id)

    await _emit_output_preview(user_id, agent_id, result)

    if agent_id == "content-video-creator":
        await _emit_agent_progress(
            user_id,
            agent_id,
            "Review the Veo prompt below — choose Generate video or Skip (panel at bottom)",
        )
    else:
        await _emit_agent_progress(
            user_id,
            agent_id,
            f"{name} draft ready — approve or revise in the panel below",
        )

    review = await request_human_input(
        user_id or "anonymous",
        agent_id,
        name,
        phase="review",
        questions=cfg.get("review") or [],
        draft_output=result,
        run_id=run_id,
    )
    merged = {**state.get("human_answers", {}).get(agent_id, {}), **review}
    state.setdefault("human_answers", {})[agent_id] = merged

    decision = str(review.get("decision") or "").lower()
    if "regenerat" in decision:
        return {"regenerate": True}
    if review.get("notes", "").strip():
        result = {**result, "human_notes": review["notes"].strip()}
    if review.get("prompt_override", "").strip() and agent_id == "content-video-creator":
        merged["prompt_override"] = review["prompt_override"].strip()
        state["human_answers"][agent_id] = merged
    return {"regenerate": False, "result": result}


async def _llm_run(agent_id: str, state: dict[str, Any], agent_config: dict[str, Any] | None) -> dict[str, Any]:
    meta = CONTENT_AGENTS[agent_id]
    cfg = agent_config or {}
    region = _region_label(state)
    system = (
        f"You are the {meta['name']} agent in CreatorOS. {meta['task']}\n\n"
        "CRITICAL: All output MUST directly serve the creator's goal, niche, and region. "
        "Never use generic AI/SaaS/startup examples unless the niche explicitly asks for them.\n"
        f"Goal: {_goal(state)}\n"
        f"Niche: {_niche_label(state)}\n"
        f"Region / audience: {region or 'infer from goal'}\n"
        f"Human direction: {json.dumps(_human_answers(state, agent_id), ensure_ascii=False)}\n"
        "Return JSON only with a top-level \"result\" object matching your output schema."
    )
    custom = str(cfg.get("prompt") or "").strip()
    if custom:
        system += f"\n\nAdditional instructions:\n{custom}"

    payload = {
        "creator_type": state.get("creator_type"),
        "niche": state.get("niche"),
        "region": state.get("region"),
        "platforms": state.get("platforms"),
        "goal": state.get("goal"),
        "human_answers": state.get("human_answers", {}).get(agent_id, {}),
        "prior_outputs": state.get("pipeline_results", {}),
    }
    raw = await complete_json(
        system=system,
        user=json.dumps(payload, ensure_ascii=False),
        model=str(cfg.get("model") or "").strip() or None,
        temperature=cfg.get("temperature"),
    )
    return raw.get("result", raw)


async def _execute_agent_core(
    agent_id: str,
    state: dict[str, Any],
    agent_config: dict[str, Any] | None,
) -> dict[str, Any]:
    if agent_id == "content-video-creator":
        return draft_video_creator(state)
    executor = RULE_EXECUTORS[agent_id]
    try:
        if llm_configured():
            return await _llm_run(agent_id, state, agent_config)
        return executor(state)
    except LLMError:
        return executor(state)


async def run_content_agent(
    agent_id: str,
    state: dict[str, Any],
    *,
    agent_config: dict[str, Any] | None = None,
    user_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute a single content specialist agent, with optional human-in-the-loop."""
    if agent_id not in RULE_EXECUTORS:
        raise ValueError(f"Unknown content agent: {agent_id}")

    state = normalize_creator_context(state)
    cfg = agent_config or {}
    hitl_enabled = cfg.get("human_in_loop", settings.content_human_in_loop)
    use_hitl = hitl_enabled and agent_id in HITL_AGENT_IDS and user_id

    if user_id:
        from app.services.run_control import check_agent_cancelled

        check_agent_cancelled(user_id, "content-director")

    mode = "rules"
    result: dict[str, Any] = {}

    if use_hitl:
        await _emit_agent_progress(
            user_id, agent_id, f"{agent_name(agent_id)} — answer the questions in the panel below",
        )
        await _run_hitl(agent_id, state, user_id=user_id, run_id=run_id)

    for attempt in range(2 if use_hitl else 1):
        if agent_id == "content-video-creator" and not use_hitl:
            result = await rule_video_creator(state)
            mode = "veo"
            break

        await _emit_agent_progress(
            user_id, agent_id, f"{agent_name(agent_id)} — generating draft…",
        )
        core = await _execute_agent_core(agent_id, state, agent_config)
        result = core
        mode = "llm" if llm_configured() and agent_id != "content-video-creator" else "rules"

        if not use_hitl:
            break

        review = await _review_hitl(agent_id, state, result, user_id=user_id, run_id=run_id)
        if review.get("regenerate") and attempt == 0:
            continue
        result = review.get("result", result)

        if agent_id == "content-video-creator":
            decision = str(state.get("human_answers", {}).get(agent_id, {}).get("decision") or "").lower()
            if "skip" not in decision:
                result = await rule_video_creator(state)
        break

    if use_hitl:
        mode = "hitl_" + mode

    return {"agent_id": agent_id, "mode": mode, "result": result}


def build_weekly_plan(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Assemble weekly plan items from pipeline outputs."""
    strategy = _prior(state, "content-strategy")
    hooks = _prior(state, "content-hook-generator").get("hooks") or []
    schedule = _prior(state, "content-publishing").get("schedule") or []
    plan: list[dict[str, Any]] = []

    for i, day in enumerate(strategy.get("calendar") or []):
        plan.append({
            "day": day.get("day", f"Day {i + 1}"),
            "focus": day.get("focus"),
            "platforms": day.get("platforms", []),
            "hook": _item_text(hooks[i % len(hooks)], "text", "hook", "title") if hooks else None,
            "publish_slot": schedule[i]["slot"] if i < len(schedule) else None,
        })
    return plan


async def run_pipeline_sequential(
    state: dict[str, Any],
    *,
    agent_config: dict[str, Any] | None = None,
    user_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Rule-based pipeline using a while loop over CONTENT_PIPELINE."""
    state = normalize_creator_context(state)
    pipeline_results: dict[str, Any] = dict(state.get("pipeline_results") or {})
    assigned: list[str] = list(state.get("assigned_agents") or [])
    idx = 0

    while idx < len(CONTENT_PIPELINE):
        agent_id = CONTENT_PIPELINE[idx]
        step_state = {**state, "pipeline_results": pipeline_results}
        out = await run_content_agent(
            agent_id, step_state, agent_config=agent_config, user_id=user_id, run_id=run_id,
        )
        pipeline_results[agent_id] = out["result"]
        assigned.append(agent_id)
        idx += 1

    final_state = {
        **state,
        "pipeline_results": pipeline_results,
        "assigned_agents": assigned,
        "weekly_plan": build_weekly_plan({**state, "pipeline_results": pipeline_results}),
    }
    return final_state
