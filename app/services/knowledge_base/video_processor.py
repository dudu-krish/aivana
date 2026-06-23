"""Extract transcript + visual scene text from videos for embedding (no file copies)."""

from __future__ import annotations

import base64
import hashlib
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v", ".wmv"})


def collect_videos(folder: Path) -> list[Path]:
    seen: set[Path] = set()
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            seen.add(path.resolve())
    return sorted(seen, key=lambda p: str(p).lower())


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _run_ffmpeg(args: list[str], *, timeout: int = 120) -> bool:
    try:
        proc = subprocess.run(
            ["ffmpeg", *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            logger.debug("ffmpeg failed: %s", proc.stderr.decode(errors="ignore")[:400])
            return False
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("ffmpeg unavailable: %s", exc)
        return False


def _extract_audio_wav(video_path: Path, wav_path: Path) -> bool:
    return _run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_path),
        ],
        timeout=settings.kb_video_ffmpeg_timeout_seconds,
    )


def _extract_frame_jpegs(
    video_path: Path,
    out_dir: Path,
    *,
    interval_sec: float,
    max_frames: int,
) -> list[tuple[float, Path]]:
    pattern = out_dir / "frame_%04d.jpg"
    ok = _run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps=1/{max(interval_sec, 1)}",
            "-frames:v",
            str(max_frames),
            str(pattern),
        ],
        timeout=settings.kb_video_ffmpeg_timeout_seconds,
    )
    if not ok:
        return []
    frames: list[tuple[float, Path]] = []
    for i, frame_path in enumerate(sorted(out_dir.glob("frame_*.jpg"))):
        timestamp = round(i * interval_sec, 2)
        frames.append((timestamp, frame_path))
    return frames


def _transcribe_wav(wav_path: Path) -> str:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key or not wav_path.is_file() or wav_path.stat().st_size == 0:
        return ""
    try:
        with wav_path.open("rb") as fh:
            response = httpx.post(
                f"{settings.openai_base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (wav_path.name, fh, "audio/wav")},
                data={"model": settings.kb_whisper_model, "response_format": "text"},
                timeout=settings.kb_video_whisper_timeout_seconds,
            )
        response.raise_for_status()
        return (response.text or "").strip()
    except Exception as exc:
        logger.warning("Whisper transcription failed for %s: %s", wav_path.name, exc)
        return ""


def _describe_frame_jpeg(jpeg_bytes: bytes, timestamp_sec: float) -> str:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key or not settings.kb_video_describe_frames:
        return f"Video frame at {timestamp_sec:.0f}s"
    b64 = base64.standard_b64encode(jpeg_bytes).decode("ascii")
    try:
        response = httpx.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.planner_model,
                "temperature": 0.1,
                "max_tokens": 200,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Describe this video frame at {timestamp_sec:.1f}s in 1-2 sentences "
                                    "for search indexing. Focus on visible actions, objects, text on screen, "
                                    "and setting."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ],
                    }
                ],
            },
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        return (
            response.json()["choices"][0]["message"]["content"].strip()
            or f"Video frame at {timestamp_sec:.0f}s"
        )
    except Exception as exc:
        logger.warning("Frame description failed at %ss: %s", timestamp_sec, exc)
        return f"Video frame at {timestamp_sec:.0f}s"


def _build_video_document_text(
    *,
    filename: str,
    transcript: str,
    frame_scenes: list[dict[str, Any]],
) -> str:
    parts = [f"# Video: {filename}"]
    if transcript:
        parts.append("## Transcript\n" + transcript)
    if frame_scenes:
        lines = [f"[{s['timestamp_sec']:02.0f}s] {s['description']}" for s in frame_scenes]
        parts.append("## Visual scenes\n" + "\n".join(lines))
    if len(parts) == 1:
        parts.append(
            "## Note\nVideo indexed by filename only. Install ffmpeg and set OPENAI_API_KEY "
            "for transcript + visual scene embeddings."
        )
    return "\n\n".join(parts)


def process_video(path: Path) -> dict[str, Any]:
    """Read a video file in place; return text + metadata for hierarchical embedding."""
    filename = path.name
    transcript = ""
    frame_scenes: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="kb-video-") as tmp:
        tmp_dir = Path(tmp)
        wav_path = tmp_dir / "audio.wav"

        if ffmpeg_available():
            if _extract_audio_wav(path, wav_path):
                transcript = _transcribe_wav(wav_path)

            frame_dir = tmp_dir / "frames"
            frame_dir.mkdir(exist_ok=True)
            for timestamp_sec, frame_path in _extract_frame_jpegs(
                path,
                frame_dir,
                interval_sec=settings.kb_video_frame_interval_sec,
                max_frames=settings.kb_video_max_frames,
            ):
                description = _describe_frame_jpeg(frame_path.read_bytes(), timestamp_sec)
                frame_scenes.append(
                    {
                        "timestamp_sec": timestamp_sec,
                        "description": description,
                    }
                )
        else:
            logger.info("ffmpeg not found — video %s indexed with metadata only", filename)

    body = _build_video_document_text(
        filename=filename,
        transcript=transcript,
        frame_scenes=frame_scenes,
    )
    content_hash = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()
    return {
        "text": body,
        "content_hash": content_hash,
        "metadata": {
            "filename": filename,
            "modality": "video",
            "transcript_chars": len(transcript),
            "frame_count": len(frame_scenes),
            "has_transcript": bool(transcript),
            "has_visual_scenes": bool(frame_scenes),
            "ffmpeg": ffmpeg_available(),
        },
        "video_segments": _video_segments(transcript, frame_scenes),
    }


def _video_segments(
    transcript: str,
    frame_scenes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Separate transcript vs visual segments for targeted retrieval metadata."""
    segments: list[dict[str, Any]] = []
    if transcript:
        segments.append(
            {
                "segment_type": "transcript",
                "text": transcript,
                "timestamp_sec": None,
            }
        )
    for scene in frame_scenes:
        segments.append(
            {
                "segment_type": "visual",
                "text": scene["description"],
                "timestamp_sec": scene["timestamp_sec"],
            }
        )
    return segments
