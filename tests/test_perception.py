"""Tests for Perception micro-agents."""

import asyncio
from pathlib import Path

from pypdf import PdfWriter

from app.agents.perception import (
    PerceptionAgent,
    _collect_pdfs,
    _resolve_folder,
    _rule_perceive,
)
from app.agents.perception_registry import PERCEPTION_AGENTS, is_perception_agent
from app.services.tenant import TenantContext


def _tenant() -> TenantContext:
    t = TenantContext(user_id="test-user", email="t@example.com", name="Test")
    t.ensure_dirs()
    return t


def _make_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        writer.write(fh)


def test_registry_has_twenty_five_agents() -> None:
    assert len(PERCEPTION_AGENTS) == 25


def test_is_perception_agent() -> None:
    assert is_perception_agent("read-text")
    assert not is_perception_agent("planner")


def test_read_text() -> None:
    out = _rule_perceive("read-text", "Hello world", _tenant())
    assert out["result"]["content"] == "Hello world"
    assert out["result"]["word_count"] == 2


def test_log_reader() -> None:
    logs = "2024-01-01 10:00:00 INFO Server started\nplain line"
    out = _rule_perceive("log-reader", logs, _tenant())
    assert out["result"]["line_count"] == 2


def test_html_reader() -> None:
    html = "<html><head><title>Hi</title></head><body><p>Hello</p></body></html>"
    out = _rule_perceive("html-reader", html, _tenant())
    assert "Hello" in out["result"]["text"]
    assert out["result"]["title"] == "Hi"


def test_collect_pdfs_in_folder() -> None:
    tenant = _tenant()
    folder = tenant.downloads_dir / "pdf-batch"
    nested = folder / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    _make_pdf(folder / "a.pdf")
    _make_pdf(nested / "b.pdf")

    resolved = _resolve_folder("downloads/pdf-batch", tenant)
    assert resolved is not None
    pdfs = _collect_pdfs(resolved)
    assert len(pdfs) == 2


def test_read_pdf_folder_batch() -> None:
    tenant = _tenant()
    _make_pdf(tenant.invoices_dir / "invoice-one.pdf")
    _make_pdf(tenant.invoices_dir / "invoice-two.pdf")

    agent = PerceptionAgent(tenant, "read-pdf")
    result = asyncio.run(agent.run(folder_path="invoices"))
    assert result["status"] == "completed"
    payload = result["result"]
    assert payload["pdf_count"] == 2
    assert payload["read_ok"] == 2
    assert len(payload["documents"]) == 2
