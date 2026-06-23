"""Stream documents from folders, CSV, databases, and SharePoint without persisting files."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from collections.abc import Iterator
from itertools import chain
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from app.agents.perception import _collect_pdfs, _read_pdf, _resolve_folder
from app.config import settings
from app.services.tenant import TenantContext

logger = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _pdf_bytes_to_text(data: bytes) -> str:
    import tempfile

    from pypdf import PdfReader

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        reader = PdfReader(tmp.name)
        return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()


def folder_pdf_count(folder: str, tenant: TenantContext) -> tuple[Path | None, int]:
    """Resolve folder and count PDFs recursively (includes all subfolders)."""
    resolved = _resolve_folder(folder, tenant)
    if not resolved:
        return None, 0
    return resolved, len(_collect_pdfs(resolved))


def stream_folder_pdfs(folder: str, tenant: TenantContext) -> Iterator[dict[str, Any]]:
    resolved, _ = folder_pdf_count(folder, tenant)
    if not resolved:
        logger.warning("PDF folder not found: %r (tenant=%s)", folder, tenant.user_id)
        return
    for pdf_path in _collect_pdfs(resolved):
        try:
            text = _read_pdf(pdf_path)
            rel = str(pdf_path.relative_to(resolved)).replace("\\", "/")
            yield {
                "document_id": f"pdf:{rel}",
                "source_type": "folder_pdf",
                "source_uri": rel,
                "text": text,
                "metadata": {"filename": pdf_path.name, "folder": folder},
                "content_hash": _content_hash(text),
            }
        except Exception as exc:
            logger.warning("PDF read failed %s: %s", pdf_path, exc)


def stream_folder_videos(folder: str, tenant: TenantContext) -> Iterator[dict[str, Any]]:
    from app.services.knowledge_base.video_processor import collect_videos, process_video

    resolved, _ = folder_video_count(folder, tenant)
    if not resolved:
        logger.warning("Video folder not found: %r (tenant=%s)", folder, tenant.user_id)
        return
    for video_path in collect_videos(resolved):
        try:
            processed = process_video(video_path)
            rel = str(video_path.relative_to(resolved)).replace("\\", "/")
            yield {
                "document_id": f"video:{rel}",
                "source_type": "folder_video",
                "source_uri": rel,
                "text": processed["text"],
                "metadata": {
                    **processed.get("metadata", {}),
                    "folder": folder,
                },
                "content_hash": processed["content_hash"],
                "video_segments": processed.get("video_segments") or [],
            }
        except Exception as exc:
            logger.warning("Video processing failed %s: %s", video_path, exc)


def folder_video_count(folder: str, tenant: TenantContext) -> tuple[Path | None, int]:
    from app.services.knowledge_base.video_processor import collect_videos

    resolved = _resolve_folder(folder, tenant)
    if not resolved:
        return None, 0
    return resolved, len(collect_videos(resolved))


def stream_folder_media(
    folder: str,
    tenant: TenantContext,
    *,
    include_pdfs: bool = True,
    include_videos: bool = False,
) -> Iterator[dict[str, Any]]:
    streams: list[Iterator[dict[str, Any]]] = []
    if include_pdfs:
        streams.append(stream_folder_pdfs(folder, tenant))
    if include_videos:
        streams.append(stream_folder_videos(folder, tenant))
    yield from chain.from_iterable(streams)


def stream_csv(source: str, tenant: TenantContext) -> Iterator[dict[str, Any]]:
    resolved = _resolve_folder(source, tenant)
    path = None
    if resolved and resolved.is_file() and resolved.suffix.lower() == ".csv":
        path = resolved
    else:
        for base in (tenant.downloads_dir, tenant.invoices_dir, tenant.scraped_data_dir):
            candidate = base / source.strip()
            if candidate.is_file():
                path = candidate
                break
    text = path.read_text(encoding="utf-8", errors="ignore") if path else source
    reader = csv.DictReader(io.StringIO(text))
    for i, row in enumerate(reader):
        body = json.dumps(row, ensure_ascii=False)
        yield {
            "document_id": f"csv:row-{i}",
            "source_type": "csv",
            "source_uri": str(path or "inline"),
            "text": body,
            "metadata": {"row_index": i},
            "content_hash": _content_hash(body),
        }


def stream_database(connection_url: str, query: str, *, batch_size: int = 200) -> Iterator[dict[str, Any]]:
    if not connection_url.strip():
        return
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        logger.error("sqlalchemy required for database source: pip install sqlalchemy")
        return

    engine = create_engine(connection_url)
    with engine.connect() as conn:
        result = conn.execution_options(stream_results=True).execute(text(query))
        cols = list(result.keys())
        batch: list[dict[str, Any]] = []
        for i, row in enumerate(result):
            record = {cols[j]: row[j] for j in range(len(cols))}
            body = json.dumps(record, ensure_ascii=False, default=str)
            batch.append(
                {
                    "document_id": f"db:row-{i}",
                    "source_type": "database",
                    "source_uri": query[:120],
                    "text": body,
                    "metadata": {"row_index": i},
                    "content_hash": _content_hash(body),
                }
            )
            if len(batch) >= batch_size:
                yield from batch
                batch = []
        if batch:
            yield from batch


def stream_sharepoint_pdfs(
    *,
    site_url: str,
    folder_path: str,
    access_token: str,
) -> Iterator[dict[str, Any]]:
    """Stream PDF content from SharePoint via Microsoft Graph (in-memory, no local download)."""
    if not access_token or not site_url:
        return
    headers = {"Authorization": f"Bearer {access_token}"}
    base = settings.sharepoint_graph_base.rstrip("/")

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        site_resp = client.get(f"{base}/sites/{site_url}", headers=headers)
        site_resp.raise_for_status()
        site_id = site_resp.json()["id"]

        items_url = f"{base}/sites/{site_id}/drive/root:/{folder_path.strip('/')}:/children"
        while items_url:
            listing = client.get(items_url, headers=headers)
            listing.raise_for_status()
            payload = listing.json()
            for item in payload.get("value", []):
                name = item.get("name", "")
                if item.get("folder"):
                    sub = f"{folder_path.strip('/')}/{name}"
                    yield from stream_sharepoint_pdfs(
                        site_url=site_url, folder_path=sub, access_token=access_token
                    )
                    continue
                if not name.lower().endswith(".pdf"):
                    continue
                item_id = item["id"]
                content_url = f"{base}/sites/{site_id}/drive/items/{item_id}/content"
                pdf_resp = client.get(content_url, headers=headers)
                pdf_resp.raise_for_status()
                text = _pdf_bytes_to_text(pdf_resp.content)
                doc_id = f"sharepoint:{folder_path}/{name}"
                yield {
                    "document_id": doc_id,
                    "source_type": "sharepoint",
                    "source_uri": doc_id,
                    "text": text,
                    "metadata": {"filename": name, "sharepoint_path": folder_path},
                    "content_hash": _content_hash(text),
                }
            items_url = payload.get("@odata.nextLink")


def stream_excel_as_rows(source: str, tenant: TenantContext) -> Iterator[dict[str, Any]]:
    for base in (tenant.downloads_dir, tenant.invoices_dir):
        candidate = base / source.strip()
        if candidate.is_file() and candidate.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(candidate)
            for i, row in df.fillna("").astype(str).to_dict(orient="index").items():
                body = json.dumps(row, ensure_ascii=False)
                yield {
                    "document_id": f"excel:row-{i}",
                    "source_type": "csv",
                    "source_uri": str(candidate),
                    "text": body,
                    "metadata": {"row_index": i},
                    "content_hash": _content_hash(body),
                }
            return
