"""Perception micro-agents — read and parse input sources with LLM + rule fallback."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pandas as pd
from bs4 import BeautifulSoup

from app.agents.base import BaseAgent
from app.agents.perception_registry import PERCEPTION_AGENTS, agent_name
from app.services.event_bus import event_bus
from app.services.llm import LLMError, complete_json, llm_configured
from app.services.model_router import apply_model_routing
from app.config import settings
from app.services.tenant import TenantContext

_TENANT_FOLDER_ALIASES = frozenset(
    {"invoices", "payments", "gmail_attachments", "downloads", "scraped_data", "credentials"}
)

_EMAIL_HEADER_RE = re.compile(r"^(From|To|Cc|Subject|Date):\s*(.+)$", re.I | re.M)
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}[^\s]*)\s+(?P<level>\w+)?\s*(?P<msg>.*)$"
)
_QR_URL_RE = re.compile(r"https?://[^\s]+", re.I)
_BARCODE_RE = re.compile(r"\b\d{8,14}\b")
_TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.M)
_FORM_FIELD_RE = re.compile(r"^([A-Za-z][\w\s/-]{1,40}):\s*(.+)$", re.M)


def _tenant_bases(tenant: TenantContext) -> tuple[Path, ...]:
    return (
        tenant.root,
        tenant.downloads_dir,
        tenant.invoices_dir,
        tenant.payments_dir,
        tenant.gmail_attachments_dir,
        tenant.scraped_data_dir,
        settings.invoices_dir,
        settings.payments_dir,
        settings.gmail_attachments_dir,
    )


def _resolve_path(source: str, tenant: TenantContext) -> Path | None:
    raw = source.strip().strip('"').strip("'")
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return p.resolve()
    for base in _tenant_bases(tenant)[1:]:
        candidate = base / raw
        if candidate.is_file():
            return candidate.resolve()
    return None


def _resolve_folder(source: str, tenant: TenantContext) -> Path | None:
    raw = source.strip().strip('"').strip("'").replace("\\", "/")
    if not raw:
        return None
    if raw in {".", "root", "all", "*", "~"}:
        return tenant.root.resolve()

    alias = raw.split("/")[0].lower()
    if alias in _TENANT_FOLDER_ALIASES:
        alias_map = {
            "invoices": tenant.invoices_dir,
            "payments": tenant.payments_dir,
            "gmail_attachments": tenant.gmail_attachments_dir,
            "downloads": tenant.downloads_dir,
            "scraped_data": tenant.scraped_data_dir,
            "credentials": tenant.credentials_dir,
        }
        base = alias_map.get(alias)
        if base is not None:
            rest = raw.split("/", 1)[1] if "/" in raw else ""
            candidate = (base / rest) if rest else base
            if candidate.is_dir():
                return candidate.resolve()

    p = Path(raw)
    if p.is_absolute() and p.is_dir():
        return p.resolve()
    for base in _tenant_bases(tenant):
        candidate = base / raw
        if candidate.is_dir():
            return candidate.resolve()
    file_path = _resolve_path(source, tenant)
    if file_path and file_path.is_file():
        return file_path.parent.resolve()
    return None


def _folder_relative(folder: Path, tenant: TenantContext) -> str:
    try:
        return str(folder.resolve().relative_to(tenant.root.resolve()))
    except ValueError:
        return str(folder)


def _collect_pdfs(folder: Path) -> list[Path]:
    seen: set[Path] = set()
    for pattern in ("*.pdf", "*.PDF"):
        for path in folder.rglob(pattern):
            if path.is_file():
                seen.add(path.resolve())
    return sorted(seen, key=lambda p: str(p).lower())


def _read_pdf_document(path: Path, *, root_folder: Path | None = None) -> dict[str, Any]:
    try:
        text = _read_pdf(path)
        rel = str(path.relative_to(root_folder)) if root_folder else path.name
        return {
            "filename": path.name,
            "path": str(path),
            "relative_path": rel.replace("\\", "/"),
            "pages_estimate": max(1, text.count("\f") + 1),
            "char_count": len(text),
            "content": text,
            "size_bytes": path.stat().st_size,
            "status": "ok",
        }
    except Exception as exc:
        return {
            "filename": path.name,
            "path": str(path),
            "status": "error",
            "error": str(exc),
            "content": "",
        }


def _is_url(source: str) -> bool:
    try:
        parsed = urlparse(source.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parts = [node.text for node in root.findall(".//w:t", ns) if node.text]
    return "\n".join(parts).strip()


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return path.read_bytes()[:2000].decode("utf-8", errors="ignore")
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _parse_csv_content(text: str) -> dict[str, Any]:
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return {"columns": [], "rows": [], "row_count": 0}
    return {"columns": rows[0], "rows": rows[1:51], "row_count": max(0, len(rows) - 1)}


def _parse_html(content: str) -> dict[str, Any]:
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    links = [{"href": a.get("href"), "text": a.get_text(strip=True)} for a in soup.find_all("a", href=True)]
    return {"text": text[:8000], "links": links[:30], "title": soup.title.get_text(strip=True) if soup.title else ""}


def _parse_email(content: str) -> dict[str, Any]:
    if content.lstrip().lower().startswith(("from:", "subject:", "to:")):
        headers = {}
        for m in _EMAIL_HEADER_RE.finditer(content):
            headers[m.group(1).lower()] = m.group(2).strip()
        body_text = content.split("\n\n", 1)[-1].strip() if "\n\n" in content else content
        return {"headers": headers, "body": body_text[:6000]}
    try:
        msg = BytesParser(policy=policy.default).parsebytes(content.encode("utf-8", errors="ignore"))
        return {
            "headers": {
                "from": str(msg.get("From", "")),
                "to": str(msg.get("To", "")),
                "subject": str(msg.get("Subject", "")),
                "date": str(msg.get("Date", "")),
            },
            "body": (msg.get_body(preferencelist=("plain", "html")) or msg).get_content()[:6000],
        }
    except Exception:
        return {"headers": {}, "body": content[:6000]}


def _parse_logs(content: str) -> dict[str, Any]:
    entries = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LOG_LINE_RE.match(line)
        if m:
            entries.append(
                {
                    "timestamp": m.group("ts"),
                    "level": (m.group("level") or "INFO").upper(),
                    "message": m.group("msg").strip(),
                }
            )
        else:
            entries.append({"timestamp": None, "level": "INFO", "message": line})
    return {"entries": entries[:200], "line_count": len(entries)}


def _parse_tables(content: str) -> dict[str, Any]:
    markdown_rows = [r.strip() for r in _TABLE_ROW_RE.findall(content)]
    if markdown_rows:
        cells = [[c.strip() for c in row.strip("|").split("|")] for row in markdown_rows]
        return {"format": "markdown", "rows": cells[:50]}
    if "," in content and "\n" in content:
        parsed = _parse_csv_content(content)
        parsed["format"] = "csv"
        return parsed
    soup = BeautifulSoup(content, "html.parser")
    tables = []
    for table in soup.find_all("table")[:5]:
        rows = []
        for tr in table.find_all("tr"):
            rows.append([td.get_text(strip=True) for td in tr.find_all(["td", "th"])])
        if rows:
            tables.append(rows)
    return {"format": "html", "tables": tables}


def _parse_form(content: str) -> dict[str, Any]:
    fields = [{"label": m.group(1).strip(), "value": m.group(2).strip()} for m in _FORM_FIELD_RE.finditer(content)]
    return {"fields": fields[:100], "field_count": len(fields)}


def _file_meta(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": stat.st_size,
        "extension": path.suffix.lower(),
    }


def _rule_perceive(agent_id: str, source: str, tenant: TenantContext) -> dict[str, Any]:
    source = source.strip()
    if not source:
        return {"status": "error", "message": "No input source provided", "result": {}}

    path = _resolve_path(source, tenant)

    if agent_id == "read-text":
        return {
            "result": {
                "content": source,
                "char_count": len(source),
                "word_count": len(source.split()),
            }
        }

    if agent_id == "read-pdf":
        return {
            "status": "error",
            "message": "Read PDF requires a folder path; use the batch reader.",
            "result": {},
        }

    if agent_id == "read-word":
        if path and path.suffix.lower() == ".docx":
            text = _read_docx(path)
            return {"result": {"content": text, **_file_meta(path)}}
        return {"result": {"content": source, "note": "Treated as inline document text"}}

    if agent_id == "read-excel":
        if path and path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path)
            preview = df.head(50).fillna("").astype(str).to_dict(orient="records")
            return {
                "result": {
                    "columns": list(df.columns),
                    "rows": preview,
                    "row_count": len(df),
                    **_file_meta(path),
                }
            }
        return {"status": "error", "message": "Excel file not found. Provide a path under your workspace.", "result": {}}

    if agent_id == "read-csv":
        if path and path.suffix.lower() == ".csv":
            text = path.read_text(encoding="utf-8", errors="ignore")
        else:
            text = source
        parsed = _parse_csv_content(text)
        return {"result": {"content": text[:4000], **parsed}}

    if agent_id == "read-image":
        if path and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            return {"result": {"content": f"Image file: {path.name}", **_file_meta(path), "detected": "image"}}
        return {"result": {"content": source, "detected": "image_reference"}}

    if agent_id == "ocr":
        content = path.read_text(encoding="utf-8", errors="ignore") if path and path.suffix.lower() == ".txt" else source
        return {"result": {"text": content, "confidence": 0.7, "mode": "rules"}}

    if agent_id == "read-barcode":
        matches = _BARCODE_RE.findall(source)
        return {"result": {"barcodes": matches, "primary": matches[0] if matches else None}}

    if agent_id == "read-qr-code":
        urls = _QR_URL_RE.findall(source)
        return {"result": {"payload": urls[0] if urls else source.strip(), "urls": urls}}

    if agent_id == "read-audio":
        if path and path.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
            return {"result": {"content": f"Audio file: {path.name}", **_file_meta(path)}}
        return {"result": {"content": source, "note": "Provide an audio file path"}}

    if agent_id == "speech-to-text":
        if path and path.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg"):
            return {
                "result": {
                    "transcript": source if not path else f"[Audio: {path.name} — configure Whisper for full STT]",
                    "file": _file_meta(path),
                }
            }
        return {"result": {"transcript": source, "mode": "inline_text"}}

    if agent_id == "video-frame-extractor":
        if path and path.suffix.lower() in (".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v", ".wmv"):
            from app.services.knowledge_base.video_processor import process_video

            processed = process_video(path)
            return {
                "result": {
                    "frames": [
                        {
                            "index": i,
                            "timestamp_sec": seg.get("timestamp_sec") or 0,
                            "description": seg.get("text", ""),
                        }
                        for i, seg in enumerate(processed.get("video_segments") or [])
                        if seg.get("segment_type") == "visual"
                    ],
                    "transcript": next(
                        (
                            seg.get("text", "")
                            for seg in processed.get("video_segments") or []
                            if seg.get("segment_type") == "transcript"
                        ),
                        "",
                    ),
                    "combined_text": processed.get("text", ""),
                    **_file_meta(path),
                    **processed.get("metadata", {}),
                }
            }
        return {"result": {"frames": [], "note": source[:500]}}

    if agent_id == "face-detector":
        faces = re.findall(r"\bface[s]?\b", source, re.I)
        return {"result": {"face_count": len(faces) or (1 if "person" in source.lower() else 0), "summary": source[:500]}}

    if agent_id == "object-detector":
        objects = re.findall(r"\b(box|car|person|phone|laptop|document|table|chair|bottle)\b", source, re.I)
        return {"result": {"objects": list(dict.fromkeys(objects)) or ["unknown"], "summary": source[:500]}}

    if agent_id == "handwriting-reader":
        return {"result": {"text": source, "confidence": 0.55, "mode": "rules"}}

    if agent_id == "table-detector":
        return {"result": _parse_tables(source)}

    if agent_id == "form-reader":
        return {"result": _parse_form(source)}

    if agent_id == "screenshot-reader":
        if path:
            return {"result": {"content": f"Screenshot: {path.name}", "ocr_text": source, **_file_meta(path)}}
        return {"result": {"content": source, "ocr_text": source[:6000]}}

    if agent_id == "html-reader":
        if _is_url(source):
            return {"status": "error", "message": "Use API Reader for URLs or paste HTML directly.", "result": {}}
        if path and path.suffix.lower() in (".html", ".htm"):
            content = path.read_text(encoding="utf-8", errors="ignore")
        else:
            content = source
        parsed = _parse_html(content)
        return {"result": parsed}

    if agent_id == "email-reader":
        return {"result": _parse_email(source)}

    if agent_id == "calendar-reader":
        events = []
        for line in source.splitlines():
            if re.search(r"\b\d{4}-\d{2}-\d{2}\b", line) or re.search(r"\b\d{1,2}:\d{2}\b", line):
                events.append({"raw": line.strip()})
        if "BEGIN:VEVENT" in source:
            summaries = re.findall(r"SUMMARY:(.+)", source)
            events = [{"title": s.strip()} for s in summaries]
        return {"result": {"events": events[:50], "event_count": len(events)}}

    if agent_id == "database-reader":
        try:
            data = json.loads(source)
            if isinstance(data, list):
                return {"result": {"rows": data[:50], "row_count": len(data)}}
            return {"result": {"record": data}}
        except json.JSONDecodeError:
            rows = [line.split("|") for line in source.splitlines() if "|" in line]
            return {"result": {"rows": rows[:50], "format": "delimited"}}

    if agent_id == "log-reader":
        if path:
            content = path.read_text(encoding="utf-8", errors="ignore")
        else:
            content = source
        return {"result": _parse_logs(content)}

    if agent_id == "clipboard-reader":
        return {"result": {"content": source, "char_count": len(source), "lines": source.count("\n") + 1}}

    return {"result": {"content": source[:4000]}}


async def _fetch_api(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        body: Any
        if "json" in content_type:
            body = resp.json()
        else:
            body = resp.text[:8000]
        return {
            "result": {
                "url": url,
                "status_code": resp.status_code,
                "content_type": content_type,
                "body": body,
            }
        }


_FILE_AGENTS = frozenset({
    "read-pdf", "read-word", "read-excel", "read-csv", "read-image",
    "read-audio", "speech-to-text", "video-frame-extractor", "log-reader",
})


class PerceptionAgent(BaseAgent):
    def __init__(self, tenant: TenantContext, agent_id: str) -> None:
        if agent_id not in PERCEPTION_AGENTS:
            raise ValueError(f"Unknown perception agent: {agent_id}")
        self.tenant = tenant
        self.agent_id = agent_id
        self.agent_name = agent_name(agent_id)

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, self.agent_id, self.agent_name, event_type, message, data
        )

    async def _llm_perceive(self, source: str, agent_config: dict[str, Any] | None) -> dict[str, Any]:
        meta = PERCEPTION_AGENTS[self.agent_id]
        cfg = agent_config or {}
        system = (
            f"You are the {self.agent_name} perception micro-agent. {meta['task']} "
            "Return JSON only with a top-level \"result\" object containing structured extracted content."
        )
        custom = str(cfg.get("prompt") or "").strip()
        if custom:
            system += f"\n\nAdditional instructions:\n{custom}"

        raw = await complete_json(
            system=system,
            user=json.dumps({"source": source}, ensure_ascii=False),
            model=str(cfg.get("model") or "").strip() or None,
            temperature=cfg.get("temperature"),
        )
        if "result" not in raw:
            return {"result": raw}
        return {"result": raw["result"]}

    async def _run_read_pdf(self, source: str) -> dict[str, Any]:
        folder = _resolve_folder(source, self.tenant)
        if not folder:
            return {
                "status": "error",
                "message": (
                    "Folder not found. Set a folder path such as gmail_attachments, "
                    "downloads, or invoices — relative to your workspace."
                ),
                "result": {},
            }

        pdfs = _collect_pdfs(folder)
        if not pdfs:
            return {
                "status": "error",
                "message": f"No PDF files found in folder: {_folder_relative(folder, self.tenant)}",
                "result": {"folder": str(folder), "pdf_count": 0, "documents": []},
            }

        folder_label = _folder_relative(folder, self.tenant)
        await self._emit(
            "progress",
            f"Found {len(pdfs)} PDF(s) in {folder_label}",
            {"folder": folder_label, "pdf_count": len(pdfs)},
        )

        documents: list[dict[str, Any]] = []
        for idx, pdf_path in enumerate(pdfs, start=1):
            await self._emit(
                "progress",
                f"Reading PDF {idx}/{len(pdfs)}: {pdf_path.name}",
                {"index": idx, "total": len(pdfs), "filename": pdf_path.name},
            )
            documents.append(_read_pdf_document(pdf_path, root_folder=folder))

        ok_count = sum(1 for doc in documents if doc.get("status") == "ok")
        combined_parts = [
            f"=== {doc['filename']} ===\n{doc.get('content', '')}"
            for doc in documents
            if doc.get("status") == "ok" and doc.get("content")
        ]
        combined_content = "\n\n".join(combined_parts)

        return {
            "result": {
                "folder": str(folder),
                "folder_relative": folder_label,
                "pdf_count": len(pdfs),
                "read_ok": ok_count,
                "read_errors": len(pdfs) - ok_count,
                "documents": documents,
                "combined_content": combined_content[:80000],
            }
        }

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        source = str(
            kwargs.get("folder_path") or kwargs.get("source") or kwargs.get("text") or ""
        ).strip()
        agent_config = kwargs.get("agent_config") or {}
        agent_config = apply_model_routing(
            agent_config,
            agent_id=self.agent_id,
            text=source[:8000],
            source_size=len(source),
        )

        if not source:
            await self._emit(
                "error",
                "No folder path. Add a folder containing PDFs, or connect an upstream agent.",
            )
            return {"status": "error", "message": "No folder path"}

        await self._emit("started", f"Reading input with {self.agent_name}")

        analysis: dict[str, Any]
        mode = "rules"
        try:
            if self.agent_id == "read-pdf":
                analysis = await self._run_read_pdf(source)
            elif self.agent_id == "api-reader":
                if not _is_url(source):
                    await self._emit("error", "API Reader requires an http(s) URL.")
                    return {"status": "error", "message": "Invalid API URL"}
                analysis = await _fetch_api(source)
                mode = "http"
            elif self.agent_id in _FILE_AGENTS or _resolve_path(source, self.tenant) or _resolve_folder(source, self.tenant) or not llm_configured():
                analysis = _rule_perceive(self.agent_id, source, self.tenant)
            else:
                analysis = await self._llm_perceive(source, agent_config)
                mode = "llm"
        except LLMError as exc:
            await self._emit("progress", f"LLM unavailable ({exc}); using rules")
            analysis = _rule_perceive(self.agent_id, source, self.tenant)
            mode = "rules"
        except httpx.HTTPError as exc:
            await self._emit("error", f"API request failed: {exc}")
            return {"status": "error", "message": str(exc)}

        if analysis.get("status") == "error":
            msg = analysis.get("message", "Read failed")
            await self._emit("error", msg)
            return {"status": "error", "message": msg}

        result = analysis.get("result", {})
        content_preview = json.dumps(result, ensure_ascii=False)[:240]
        await self._emit("completed", f"{self.agent_name} complete ({mode})", {"result": result, "content": content_preview})

        return {"status": "completed", "mode": mode, "result": result}
