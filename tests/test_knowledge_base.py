"""Knowledge base ingest and search tests."""

import asyncio
from pathlib import Path

from pypdf import PdfWriter

from app.services.knowledge_base.chunker import chunk_text, hierarchical_chunk, hierarchical_to_records
from app.services.knowledge_base.service import KnowledgeBaseService
from app.services.knowledge_base import turbovec_store as store
from app.services.tenant import TenantContext


def _tenant() -> TenantContext:
    t = TenantContext(user_id="kb-test-user", email="kb@test.com", name="KB Test")
    t.ensure_dirs()
    return t


def _make_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        writer.write(fh)


def test_chunk_text_splits_long_paragraphs() -> None:
    text = "word " * 500
    chunks = chunk_text(text, max_chars=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)


def test_hierarchical_chunk_links_children_to_parents() -> None:
    text = (
        "Introduction to methodology. We used a double-blind trial design. "
        "Results showed significant improvement in patient outcomes. "
        "Discussion covers limitations and future work."
    )
    blocks = hierarchical_chunk(text, parent_max_chars=120, child_max_chars=40, child_overlap=8)
    assert blocks
    records = hierarchical_to_records(blocks, document_id="doc-1")
    assert records[0]["parent_id"].startswith("doc-1__p")
    assert records[0]["children"]
    assert all(c["parent_id"] == records[0]["parent_id"] for c in records[0]["children"])


def test_search_hierarchical_returns_parent_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.tenants_dir", tmp_path / "tenants")

    tenant = TenantContext(user_id="kb-hier", email="a@b.com", name="T")
    cid = f"{tenant.user_id}:hier"
    parent_id = "doc1__p0"
    store.upsert_parents(
        cid,
        [
            {
                "parent_id": parent_id,
                "document_id": "doc1",
                "parent_text": "Refund policy allows returns within 30 days of purchase for all items.",
                "metadata": {"filename": "policy.pdf"},
            }
        ],
    )
    child_text = "returns within 30 days"
    from app.services.knowledge_base.embedder import embed_texts

    embedding = embed_texts([child_text])[0]
    store.upsert_chunks(
        cid,
        [
            {
                "chunk_id": f"{parent_id}__c0",
                "document_id": "doc1",
                "parent_id": parent_id,
                "document": child_text,
                "embedding": embedding,
                "metadata": {"parent_id": parent_id, "filename": "policy.pdf"},
                "content_hash": "h1",
            }
        ],
    )
    q_vec = embed_texts(["What is the refund policy?"])[0]
    hits = store.search_hierarchical(cid, q_vec, child_k=5, parent_k=3)
    assert hits
    assert "30 days" in hits[0]["text"]


def test_build_nested_folder_pdfs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.tenants_dir", tmp_path / "tenants")

    tenant = TenantContext(user_id="kb-nested", email="a@b.com", name="T")
    tenant.ensure_dirs()
    nested = tenant.gmail_attachments_dir / "Inbox" / "2024"
    nested.mkdir(parents=True, exist_ok=True)
    _make_pdf(nested / "policy.pdf")

    kb = KnowledgeBaseService(tenant)
    cid = kb.collection_id("nested")
    monkeypatch.setattr(
        "app.services.knowledge_base.service.doc_sources.folder_video_count",
        lambda folder, tenant: (None, 0),
    )
    result = asyncio.run(
        kb.build([{"type": "folder_pdf", "folder": "gmail_attachments"}], collection="nested")
    )
    assert result["documents_processed"] >= 1
    assert store.collection_stats(cid)["chunks"] >= 1


def test_build_and_ask_folder_pdfs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.tenants_dir", tmp_path / "tenants")

    def _fake_stream(folder: str, tenant: TenantContext):
        yield {
            "document_id": "pdf:test/doc-a.pdf",
            "source_type": "folder_pdf",
            "source_uri": "doc-a.pdf",
            "text": "Organization refund policy allows returns within 30 days of purchase.",
            "metadata": {"filename": "doc-a.pdf"},
            "content_hash": "hash-a",
        }
        yield {
            "document_id": "pdf:test/doc-b.pdf",
            "source_type": "folder_pdf",
            "source_uri": "doc-b.pdf",
            "text": "Invoice processing requires manager approval above ten thousand dollars.",
            "metadata": {"filename": "doc-b.pdf"},
            "content_hash": "hash-b",
        }

    def _fake_count(folder: str, tenant: TenantContext):
        return tenant.invoices_dir, 2

    def _fake_video_count(folder: str, tenant: TenantContext):
        return None, 0

    monkeypatch.setattr(
        "app.services.knowledge_base.service.doc_sources.folder_video_count",
        _fake_video_count,
    )
    monkeypatch.setattr(
        "app.services.knowledge_base.service.doc_sources.folder_pdf_count",
        _fake_count,
    )
    monkeypatch.setattr(
        "app.services.knowledge_base.service.doc_sources.stream_folder_pdfs",
        _fake_stream,
    )

    tenant = TenantContext(user_id="kb-t1", email="a@b.com", name="T")
    tenant.ensure_dirs()
    kb = KnowledgeBaseService(tenant)
    cid = kb.collection_id("test")

    result = asyncio.run(
        kb.build([{"type": "folder_pdf", "folder": "invoices"}], collection="test")
    )
    assert result["documents_processed"] == 2
    assert store.collection_stats(cid)["chunks"] >= 2

    answer = asyncio.run(kb.ask("What is the refund policy?", collection="test"))
    assert answer["status"] == "completed"
    assert answer.get("answer")
