"""Video embedding pipeline tests."""

import asyncio
from pathlib import Path

from app.services.knowledge_base.service import KnowledgeBaseService
from app.services.knowledge_base import turbovec_store as store
from app.services.knowledge_base.video_processor import (
    VIDEO_EXTENSIONS,
    _build_video_document_text,
    collect_videos,
    process_video,
)
from app.services.tenant import TenantContext


def test_collect_videos_recursive(tmp_path) -> None:
    folder = tmp_path / "media"
    nested = folder / "clips"
    nested.mkdir(parents=True)
    (nested / "demo.mp4").write_bytes(b"fake")
    (folder / "intro.MOV").write_bytes(b"fake")
    found = collect_videos(folder)
    assert len(found) == 2
    assert {p.name for p in found} == {"demo.mp4", "intro.MOV"}


def test_build_video_document_text_combines_transcript_and_scenes() -> None:
    text = _build_video_document_text(
        filename="training.mp4",
        transcript="Welcome to the safety briefing.",
        frame_scenes=[{"timestamp_sec": 12.0, "description": "Presenter points at fire exit map."}],
    )
    assert "training.mp4" in text
    assert "Transcript" in text
    assert "Visual scenes" in text
    assert "fire exit" in text


def test_process_video_without_ffmpeg(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.knowledge_base.video_processor.ffmpeg_available",
        lambda: False,
    )
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00")
    result = process_video(video)
    assert result["text"]
    assert result["metadata"]["modality"] == "video"
    assert result["metadata"]["ffmpeg"] is False


def test_build_video_folder_embeddings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.tenants_dir", tmp_path / "tenants")

    def _fake_process(path: Path):
        return {
            "text": f"# Video: {path.name}\n\n## Transcript\nRefund policy explained in video.",
            "content_hash": f"hash-{path.name}",
            "metadata": {
                "filename": path.name,
                "modality": "video",
                "has_transcript": True,
                "has_visual_scenes": False,
                "ffmpeg": True,
            },
            "video_segments": [{"segment_type": "transcript", "text": "Refund policy explained in video.", "timestamp_sec": None}],
        }

    monkeypatch.setattr(
        "app.services.knowledge_base.video_processor.process_video",
        _fake_process,
    )

    tenant = TenantContext(user_id="vid-t1", email="a@b.com", name="T")
    tenant.ensure_dirs()
    videos = tenant.downloads_dir / "videos"
    videos.mkdir(parents=True)
    (videos / "policy.mp4").write_bytes(b"video")

    kb = KnowledgeBaseService(tenant)
    cid = kb.collection_id("video-test")
    result = asyncio.run(
        kb.build([{"type": "folder_video", "folder": "downloads/videos"}], collection="video-test")
    )
    assert result["documents_processed"] == 1
    assert store.collection_stats(cid)["chunks"] >= 1


def test_video_extensions_cover_common_formats() -> None:
    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".webm" in VIDEO_EXTENSIONS
