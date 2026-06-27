"""Google Gemini Veo — text-to-video for CreatorOS intro clips."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class VeoError(Exception):
    pass


def veo_configured() -> bool:
    return bool(settings.gemini_api_key.strip())


def build_intro_veo_prompt(
    *,
    niche: str,
    goal: str,
    region: str,
    hook: str = "",
    script_excerpt: str = "",
    visual_notes: str = "",
    human_answers: dict[str, Any] | None = None,
) -> str:
    """Craft a cinematic Veo prompt for a regional intro video."""
    answers = human_answers or {}
    style = str(answers.get("intro_style") or "cinematic documentary").strip()
    language = str(answers.get("language") or "Assamese with English subtitles").strip()
    landmarks = str(answers.get("landmarks") or "Brahmaputra river, tea gardens, Guwahati skyline").strip()

    parts = [
        f"Cinematic {style} introduction video for a content creator.",
        f"Audience region: {region or niche}.",
        f"Creator goal: {goal}.",
        f"Language / voiceover style: {language}.",
    ]
    if hook:
        parts.append(f"Opening hook energy: {hook[:200]}.")
    if script_excerpt:
        parts.append(f"Narrative focus: {script_excerpt[:300]}.")
    if visual_notes:
        parts.append(f"Visual direction: {visual_notes[:200]}.")
    parts.append(f"Feature authentic local scenery: {landmarks}.")
    parts.append(
        "Warm golden-hour lighting, smooth drone and handheld B-roll, "
        "engaging faces from the local community, modern creator energy, "
        "no logos, no watermarks, 16:9 landscape, high fidelity."
    )
    return " ".join(parts)


async def generate_veo_video(
    prompt: str,
    *,
    output_path: Path,
    duration_seconds: int = 8,
    aspect_ratio: str = "16:9",
    model: str | None = None,
    poll_interval: float = 10.0,
    max_wait_seconds: float = 600.0,
) -> dict[str, Any]:
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        raise VeoError("GEMINI_API_KEY is not configured")

    model_id = (model or settings.veo_model).strip()
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "durationSeconds": duration_seconds,
            "sampleCount": 1,
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        start_url = f"{GEMINI_BASE}/models/{model_id}:predictLongRunning"
        start_resp = await client.post(start_url, headers=headers, json=body)
        if start_resp.status_code >= 400:
            raise VeoError(f"Veo start failed ({start_resp.status_code}): {start_resp.text[:500]}")

        operation_name = start_resp.json().get("name")
        if not operation_name:
            raise VeoError(f"Veo returned no operation name: {start_resp.text[:300]}")

        op_url = f"{GEMINI_BASE}/{operation_name.lstrip('/')}"
        elapsed = 0.0
        status_data: dict[str, Any] = {}

        while elapsed < max_wait_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            status_resp = await client.get(op_url, headers=headers)
            if status_resp.status_code >= 400:
                raise VeoError(f"Veo poll failed ({status_resp.status_code}): {status_resp.text[:500]}")
            status_data = status_resp.json()
            if status_data.get("done"):
                break
        else:
            raise VeoError("Veo generation timed out")

        if status_data.get("error"):
            raise VeoError(str(status_data["error"]))

        response = status_data.get("response") or {}
        samples = (response.get("generateVideoResponse") or {}).get("generatedSamples") or []
        if not samples:
            raise VeoError(f"Veo completed with no samples: {status_data}")

        video_uri = (samples[0].get("video") or {}).get("uri")
        if not video_uri:
            raise VeoError("Veo sample missing video URI")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        dl_resp = await client.get(video_uri, headers=headers, follow_redirects=True)
        if dl_resp.status_code >= 400:
            raise VeoError(f"Veo download failed ({dl_resp.status_code})")
        output_path.write_bytes(dl_resp.content)

        return {
            "status": "generated",
            "local_path": str(output_path),
            "video_uri": video_uri,
            "prompt": prompt,
            "model": model_id,
            "duration_seconds": duration_seconds,
        }
