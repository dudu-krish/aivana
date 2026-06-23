"""Knowledge base ingest and Q&A orchestration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from app.config import settings
from app.services.knowledge_base.chunker import hierarchical_chunk, hierarchical_to_records
from app.services.knowledge_base.embedder import embed_texts
from app.services.knowledge_base import sources as doc_sources
from app.services.knowledge_base import turbovec_store as store
from app.services.llm import LLMError, complete_json, llm_configured
from app.services.tenant import TenantContext

logger = logging.getLogger(__name__)

EMBED_BATCH = 32
INDEX_EVERY_CHUNKS = 400


class KnowledgeBaseService:
    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    def collection_id(self, name: str | None = None) -> str:
        label = (name or "org-knowledge").strip() or "org-knowledge"
        return f"{self.tenant.user_id}:{label}"

    def stats(self, collection: str | None = None) -> dict[str, Any]:
        cid = self.collection_id(collection)
        return {"collection_id": cid, **store.collection_stats(cid)}

    async def build(
        self,
        source_specs: list[dict[str, Any]],
        *,
        collection: str | None = None,
        on_progress: Callable[[str, dict[str, Any] | None], Any] | None = None,
    ) -> dict[str, Any]:
        cid = self.collection_id(collection)
        docs_processed = 0
        docs_skipped = 0
        chunks_added = 0
        pending_chunks: list[dict[str, Any]] = []
        total_chunks_pending_rebuild = 0

        async def emit(msg: str, data: dict[str, Any] | None = None) -> None:
            if on_progress:
                result = on_progress(msg, data)
                if hasattr(result, "__await__"):
                    await result

        await emit("Starting knowledge base build (AI handles reading & indexing — you keep judgment & context)")

        for spec in source_specs:
            src_type = str(spec.get("type") or "").strip().lower()
            await emit(f"Connecting source: {src_type}", {"source_type": src_type})

            iterator: Any
            if src_type in ("folder_pdf", "pdf_folder", "folder"):
                folder_key = str(spec.get("folder") or spec.get("path") or "")
                resolved, pdf_total = doc_sources.folder_pdf_count(folder_key, self.tenant)
                _, video_total = doc_sources.folder_video_count(folder_key, self.tenant)
                include_videos = bool(spec.get("include_videos"))
                if not resolved:
                    await emit(
                        f"Folder not found: {folder_key or '(empty)'} — "
                        "try gmail_attachments, downloads, invoices, or . for all workspace folders",
                        {"source_type": src_type, "folder": folder_key, "pdfs_found": 0},
                    )
                    continue
                try:
                    rel = str(resolved.relative_to(self.tenant.root))
                except ValueError:
                    rel = str(resolved)
                await emit(
                    f"Scanning {rel} — {pdf_total} PDF(s)"
                    + (f", {video_total} video(s)" if include_videos else ""),
                    {
                        "folder": rel,
                        "pdfs_found": pdf_total,
                        "videos_found": video_total if include_videos else 0,
                    },
                )
                if pdf_total == 0 and (not include_videos or video_total == 0):
                    await emit(
                        f"No PDFs or videos under {rel}",
                        {"folder": rel, "pdfs_found": pdf_total, "videos_found": video_total},
                    )
                    continue
                if include_videos and video_total:
                    await emit(
                        "Video embeddings: transcript (Whisper) + visual scenes (frame descriptions)",
                        {"videos_found": video_total},
                    )
                iterator = doc_sources.stream_folder_media(
                    folder_key,
                    self.tenant,
                    include_pdfs=pdf_total > 0,
                    include_videos=include_videos and video_total > 0,
                )
            elif src_type in ("folder_video", "video_folder", "video"):
                folder_key = str(spec.get("folder") or spec.get("path") or "")
                resolved, video_total = doc_sources.folder_video_count(folder_key, self.tenant)
                if not resolved:
                    await emit(
                        f"Video folder not found: {folder_key or '(empty)'}",
                        {"source_type": src_type, "folder": folder_key, "videos_found": 0},
                    )
                    continue
                try:
                    rel = str(resolved.relative_to(self.tenant.root))
                except ValueError:
                    rel = str(resolved)
                await emit(
                    f"Scanning {rel} for videos — found {video_total} file(s). "
                    "Extracting transcript + visual scenes for embedding…",
                    {"folder": rel, "videos_found": video_total},
                )
                if video_total == 0:
                    await emit(f"No video files under {rel}", {"folder": rel, "videos_found": 0})
                    continue
                iterator = doc_sources.stream_folder_videos(folder_key, self.tenant)
            elif src_type == "csv":
                iterator = doc_sources.stream_csv(str(spec.get("path") or spec.get("source") or ""), self.tenant)
            elif src_type == "database":
                url = str(spec.get("connection_url") or settings.kb_database_url or "")
                query = str(spec.get("query") or "SELECT * FROM documents LIMIT 1000")
                iterator = doc_sources.stream_database(url, query)
            elif src_type == "sharepoint":
                token = str(spec.get("access_token") or settings.sharepoint_access_token or "")
                iterator = doc_sources.stream_sharepoint_pdfs(
                    site_url=str(spec.get("site_url") or settings.sharepoint_site_url or ""),
                    folder_path=str(spec.get("folder_path") or spec.get("folder") or ""),
                    access_token=token,
                )
            else:
                await emit(f"Unknown source type: {src_type}")
                continue

            for doc in iterator:
                doc_id = doc["document_id"]
                if store.document_hash(cid, doc_id) == doc.get("content_hash"):
                    docs_skipped += 1
                    continue

                store.delete_document_index(cid, doc_id)

                text = (doc.get("text") or "").strip()
                if not text:
                    meta = doc.get("metadata") or {}
                    filename = meta.get("filename") or doc.get("source_uri") or doc_id
                    text = (
                        f"[PDF indexed — no extractable text] File: {filename}. "
                        f"Source: {doc.get('source_uri', '')}"
                    )

                blocks = hierarchical_chunk(
                    text,
                    parent_max_chars=settings.kb_parent_max_chars,
                    child_max_chars=settings.kb_child_max_chars,
                    child_overlap=settings.kb_child_overlap,
                )
                hierarchy = hierarchical_to_records(blocks, document_id=doc_id)
                base_meta = {
                    **(doc.get("metadata") or {}),
                    "source_type": doc.get("source_type"),
                    "source_uri": doc.get("source_uri"),
                }

                parents_batch: list[dict[str, Any]] = []
                for record in hierarchy:
                    parents_batch.append(
                        {
                            "parent_id": record["parent_id"],
                            "document_id": doc_id,
                            "parent_text": record["parent_text"],
                            "metadata": base_meta,
                        }
                    )
                    for child in record["children"]:
                        pending_chunks.append(
                            {
                                "chunk_id": child["child_id"],
                                "document_id": doc_id,
                                "parent_id": child["parent_id"],
                                "document": child["child_text"],
                                "embedding": None,
                                "metadata": {
                                    **base_meta,
                                    "parent_id": child["parent_id"],
                                    "child_index": child["child_index"],
                                },
                                "content_hash": doc.get("content_hash"),
                                "_text_for_embed": child["child_text"],
                            }
                        )

                if parents_batch:
                    store.upsert_parents(cid, parents_batch)

                if len(pending_chunks) >= EMBED_BATCH:
                    texts = [p.pop("_text_for_embed") for p in pending_chunks]
                    vectors = embed_texts(texts)
                    for p, vec in zip(pending_chunks, vectors):
                        p["embedding"] = vec
                    n = store.upsert_chunks(cid, pending_chunks, rebuild_index=False)
                    chunks_added += n
                    total_chunks_pending_rebuild += n
                    pending_chunks = []
                    if total_chunks_pending_rebuild >= INDEX_EVERY_CHUNKS:
                        store.rebuild_turbovec_index(cid)
                        total_chunks_pending_rebuild = 0
                        await emit(f"Indexed {chunks_added} child chunks (turbovec)", {"chunks": chunks_added})

                store.mark_document_indexed(
                    cid,
                    doc_id,
                    source_type=str(doc.get("source_type") or src_type),
                    source_uri=str(doc.get("source_uri") or ""),
                    content_hash=str(doc.get("content_hash") or ""),
                    indexed_at=datetime.now(timezone.utc).isoformat(),
                )
                docs_processed += 1
                if docs_processed % 10 == 0:
                    await emit(
                        f"Processed {docs_processed} documents ({chunks_added} chunks)",
                        {"documents": docs_processed, "chunks": chunks_added},
                    )

        if pending_chunks:
            texts = [p.pop("_text_for_embed") for p in pending_chunks]
            vectors = embed_texts(texts)
            for p, vec in zip(pending_chunks, vectors):
                p["embedding"] = vec
            chunks_added += store.upsert_chunks(cid, pending_chunks, rebuild_index=False)

        store.rebuild_turbovec_index(cid)
        stats = store.collection_stats(cid)
        summary = {
            "status": "completed",
            "collection_id": cid,
            "documents_processed": docs_processed,
            "documents_skipped": docs_skipped,
            "chunks_indexed": chunks_added,
            **stats,
            "moravec_note": (
                "AI indexed repetitive reading and pattern storage. "
                "You apply common sense, social context, and final decisions."
            ),
        }
        await emit(
            f"Knowledge base ready — {stats['documents']} documents, "
            f"{stats.get('parents', 0)} parent sections, {stats.get('children', stats['chunks'])} child chunks",
            summary,
        )
        return summary

    async def ask(
        self,
        question: str,
        *,
        collection: str | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            return {"status": "error", "message": "Question is required"}

        cid = self.collection_id(collection)
        stats = store.collection_stats(cid)
        if stats["chunks"] == 0:
            return {"status": "error", "message": "Knowledge base is empty. Run a build workflow first."}

        parent_k = top_k or settings.kb_ask_parent_top_k
        q_vec = embed_texts([question])[0]
        hits = store.search_hierarchical(
            cid,
            q_vec,
            child_k=settings.kb_ask_child_candidates,
            parent_k=parent_k,
        )
        context = "\n\n---\n\n".join(h["text"] for h in hits if h.get("text"))

        answer = ""
        mode = "hierarchical_retrieval"
        if llm_configured():
            try:
                raw = await complete_json(
                    system=(
                        "You answer questions using ONLY the provided organization knowledge context. "
                        "Each section is a full parent passage retrieved via hierarchical RAG "
                        "(precise child match → full section context). "
                        'Return JSON: {"answer": "your answer", "confidence": "high|medium|low"}. '
                        "If the answer is not in the context, say you do not have enough information."
                    ),
                    user=json.dumps({"question": question, "context": context[:14000]}, ensure_ascii=False),
                    model=settings.planner_model,
                    temperature=0.1,
                )
                answer = str(raw.get("answer") or "")
                mode = "hierarchical_rag"
            except LLMError:
                answer = hits[0]["text"][:800] if hits else ""
        else:
            answer = hits[0]["text"][:800] if hits else "No matching content found."

        return {
            "status": "completed",
            "question": question,
            "answer": answer,
            "mode": mode,
            "collection_id": cid,
            "retrieval": "hierarchical_parent_child",
            "sources": [
                {
                    "parent_id": h.get("parent_id"),
                    "document_id": h.get("document_id"),
                    "score": h.get("score"),
                    "preview": (h.get("preview") or h.get("text") or "")[:220],
                    "metadata": h.get("metadata"),
                    "retrieval_level": h.get("retrieval_level", "parent"),
                }
                for h in hits
            ],
        }
