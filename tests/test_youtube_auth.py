"""Tests for YouTube connection storage."""

from app.services.database import init_db, save_youtube_connection, get_youtube_connection, clear_youtube_connection


def test_youtube_connection_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.db_path", tmp_path / "agent.db")
    init_db()
    save_youtube_connection(
        "user-1",
        channel_id="UC123",
        channel_title="My Channel",
        channel_url="https://www.youtube.com/channel/UC123",
        subscriber_count=1000,
    )
    row = get_youtube_connection("user-1")
    assert row is not None
    assert row["channel_title"] == "My Channel"
    clear_youtube_connection("user-1")
    assert get_youtube_connection("user-1") is None
