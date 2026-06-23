"""Shared pytest fixtures — ensure SQLite schema exists in CI and local runs."""

from __future__ import annotations

import pytest

from app.services.database import init_db


@pytest.fixture(autouse=True)
def _init_test_database(tmp_path, monkeypatch):
    """Isolated DB + data dirs; creates agent_results and related tables."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_dir", data_dir)
    monkeypatch.setattr("app.config.settings.tenants_dir", data_dir / "tenants")
    monkeypatch.setattr("app.config.settings.db_path", data_dir / "agent.db")
    init_db()
