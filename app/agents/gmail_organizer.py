"""
Gmail Organizer Agent

1. User grants OAuth consent to connect Gmail
2. Scan all emails and attachments
3. Analyze and categorize content
4. Apply Gmail labels so messages appear under each category
5. Create category folders and file attachments
6. Build category breakdown for graphical display
"""

from __future__ import annotations

import base64
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgent
from app.services.event_bus import event_bus
from app.services.gmail_auth import get_gmail_service
from app.services.tenant import TenantContext

AGENT_ID = "gmail-organizer"
AGENT_NAME = "Gmail Organizer"
GMAIL_LABEL_PREFIX = "Agent Studio/"

# Keyword-based categorization (extend with LLM later)
CATEGORY_RULES: dict[str, list[str]] = {
    "Invoices & Bills": [
        "invoice",
        "bill",
        "payment due",
        "amount due",
        "receipt",
        "statement",
    ],
    "Contracts & Legal": [
        "contract",
        "agreement",
        "terms",
        "legal",
        "nda",
        "signature",
    ],
    "Reports & Analytics": [
        "report",
        "analytics",
        "dashboard",
        "summary",
        "metrics",
        "kpi",
    ],
    "HR & Payroll": [
        "payroll",
        "salary",
        "payslip",
        "leave",
        "hr",
        "onboarding",
    ],
    "Marketing": [
        "newsletter",
        "promotion",
        "campaign",
        "marketing",
        "unsubscribe",
        "offer",
    ],
    "Support & Callbacks": [
        "support",
        "call back",
        "callback",
        "call me",
        "please call",
        "contact me",
        "help needed",
        "assistance",
    ],
    "Shipping & Logistics": [
        "shipment",
        "tracking",
        "delivery",
        "courier",
        "dispatch",
        "logistics",
    ],
}

ATTACHMENT_CATEGORY_HINTS: dict[str, str] = {
    ".pdf": "Documents",
    ".doc": "Documents",
    ".docx": "Documents",
    ".xls": "Spreadsheets",
    ".xlsx": "Spreadsheets",
    ".csv": "Spreadsheets",
    ".png": "Images",
    ".jpg": "Images",
    ".jpeg": "Images",
    ".zip": "Archives",
}


def _categorize_email(subject: str, snippet: str, sender: str, body: str = "") -> str:
    text = f"{subject} {snippet} {sender} {body}".lower()
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_RULES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score:
            scores[category] = score
    if scores:
        return max(scores, key=scores.get)  # type: ignore[arg-type]
    return "General"


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_email_body(payload: dict) -> str:
    chunks: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime in ("text/plain", "text/html"):
            try:
                raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            except Exception:
                raw = ""
            if mime == "text/html":
                raw = _strip_html(raw)
            if raw.strip():
                chunks.append(raw.strip())
        for sub in part.get("parts", []):
            walk(sub)

    if payload.get("body", {}).get("data"):
        walk(payload)
    for part in payload.get("parts", []):
        walk(part)

    plain = next((c for c in chunks if c), "")
    return plain[:8000]


def _categorize_attachment(filename: str, email_category: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in ATTACHMENT_CATEGORY_HINTS:
        hint = ATTACHMENT_CATEGORY_HINTS[ext]
        if hint == "Documents" and email_category != "General":
            return email_category
        return hint
    return email_category if email_category != "General" else "Other"


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)[:200]


def _resolve_scan_date(scan_date: str | None) -> date:
    if scan_date:
        raw = str(scan_date).strip()[:10]
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
    return date.today()


def _gmail_day_query(scan_day: date) -> str:
    next_day = scan_day + timedelta(days=1)
    return (
        f"after:{scan_day.year}/{scan_day.month:02d}/{scan_day.day:02d} "
        f"before:{next_day.year}/{next_day.month:02d}/{next_day.day:02d}"
    )


def _gmail_label_name(category: str) -> str:
    return f"{GMAIL_LABEL_PREFIX}{category}"


class _GmailLabelCache:
    def __init__(self, service: Any) -> None:
        self._service = service
        self._by_name: dict[str, str] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        result = self._service.users().labels().list(userId="me").execute()
        for label in result.get("labels", []):
            name = label.get("name")
            label_id = label.get("id")
            if name and label_id:
                self._by_name[name] = label_id
        self._loaded = True

    def get_or_create(self, name: str) -> str | None:
        self._load()
        if name in self._by_name:
            return self._by_name[name]
        try:
            created = (
                self._service.users()
                .labels()
                .create(
                    userId="me",
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                )
                .execute()
            )
            label_id = created.get("id")
            if label_id:
                self._by_name[name] = label_id
                return label_id
        except Exception:
            return None
        return None


def _apply_gmail_label(
    service: Any,
    label_cache: _GmailLabelCache,
    message_id: str,
    category: str,
) -> tuple[bool, str]:
    label_name = _gmail_label_name(category)
    label_id = label_cache.get_or_create(label_name)
    if not label_id:
        return False, label_name
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()
        return True, label_name
    except Exception:
        return False, label_name


class GmailOrganizerAgent(BaseAgent):
    agent_id = AGENT_ID
    agent_name = AGENT_NAME

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, AGENT_ID, AGENT_NAME, event_type, message, data
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        max_messages = int(kwargs.get("max_messages", 200))
        scan_day = _resolve_scan_date(kwargs.get("scan_date"))
        output_dir = Path(kwargs.get("output_dir", self.tenant.gmail_attachments_dir))

        await self._emit("started", "Starting Gmail scan and organization")

        try:
            service = get_gmail_service(self.tenant)
        except FileNotFoundError as exc:
            await self._emit("error", str(exc))
            return {"status": "error", "message": str(exc), "auth_required": True}
        except Exception as exc:
            await self._emit("error", f"Gmail auth failed: {exc}")
            return {"status": "error", "message": str(exc), "auth_required": True}

        query = _gmail_day_query(scan_day)
        await self._emit(
            "progress",
            f"Fetching emails from {scan_day.isoformat()}",
        )

        list_kwargs: dict[str, Any] = {
            "userId": "me",
            "maxResults": max_messages,
            "q": query,
        }

        result = service.users().messages().list(**list_kwargs).execute()
        messages = result.get("messages", [])

        if not messages:
            msg = f"No emails found for {scan_day.isoformat()}"
            await self._emit("completed", msg, {"email_categories": [], "attachment_categories": []})
            return {
                "status": "completed",
                "emails_processed": 0,
                "attachments_saved": 0,
                "message": msg,
                "chart_data": {"email_categories": [], "attachment_categories": []},
            }

        await self._emit("progress", f"Found {len(messages)} email(s) — reading, categorizing, and labeling")

        category_counts: dict[str, int] = {}
        attachment_counts: dict[str, int] = {}
        email_summaries: list[dict[str, Any]] = []
        processed = 0
        attachments_saved = 0
        labels_applied = 0
        label_cache = _GmailLabelCache(service)
        label_errors = 0

        for msg_meta in messages:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_meta["id"], format="full")
                .execute()
            )
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            subject = headers.get("subject", "(no subject)")
            sender = headers.get("from", "unknown")
            snippet = msg.get("snippet", "")
            body = _extract_email_body(msg.get("payload", {}))

            category = _categorize_email(subject, snippet, sender, body)
            category_counts[category] = category_counts.get(category, 0) + 1

            labeled, label_name = _apply_gmail_label(
                service, label_cache, msg_meta["id"], category
            )
            if labeled:
                labels_applied += 1
            else:
                label_errors += 1

            email_summaries.append(
                {
                    "subject": subject,
                    "from": sender,
                    "category": category,
                    "gmail_label": label_name,
                    "labeled": labeled,
                    "body_preview": body[:1200],
                }
            )

            await self._emit(
                "categorized",
                f"Email '{subject[:60]}' → {category}"
                + (f" (label: {label_name})" if labeled else " (label failed)"),
                {
                    "subject": subject,
                    "category": category,
                    "from": sender,
                    "gmail_label": label_name,
                    "labeled": labeled,
                    "body_preview": body[:1200],
                },
            )

            parts = msg.get("payload", {}).get("parts", [])
            if not parts and msg.get("payload", {}).get("body", {}).get(
                "attachmentId"
            ):
                parts = [msg["payload"]]

            for part in self._walk_parts(parts):
                filename = part.get("filename")
                body = part.get("body", {})
                attachment_id = body.get("attachmentId")
                if not filename or not attachment_id:
                    continue

                att_category = _categorize_attachment(filename, category)
                attachment_counts[att_category] = (
                    attachment_counts.get(att_category, 0) + 1
                )

                folder = output_dir / _safe_filename(att_category)
                folder.mkdir(parents=True, exist_ok=True)

                att_data = (
                    service.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=msg_meta["id"], id=attachment_id)
                    .execute()
                )
                file_bytes = base64.urlsafe_b64decode(att_data["data"])
                dest = folder / _safe_filename(filename)
                if dest.exists():
                    dest = folder / f"{msg_meta['id']}_{_safe_filename(filename)}"
                dest.write_bytes(file_bytes)
                attachments_saved += 1

                await self._emit(
                    "attachment_saved",
                    f"Saved {filename} → {att_category}/",
                    {
                        "filename": filename,
                        "category": att_category,
                        "path": str(dest.relative_to(output_dir)),
                    },
                )

            processed += 1

        if label_errors and labels_applied == 0:
            await self._emit(
                "progress",
                "Could not apply Gmail labels. Disconnect and reconnect Gmail to grant label permissions.",
            )

        chart_data = {
            "email_categories": [
                {"category": k, "count": v}
                for k, v in sorted(category_counts.items(), key=lambda x: -x[1])
            ],
            "attachment_categories": [
                {"category": k, "count": v}
                for k, v in sorted(attachment_counts.items(), key=lambda x: -x[1])
            ],
            "email_summaries": email_summaries,
        }

        summary = {
            "status": "completed",
            "emails_processed": processed,
            "attachments_saved": attachments_saved,
            "labels_applied": labels_applied,
            "scan_date": scan_day.isoformat(),
            "category_counts": category_counts,
            "attachment_counts": attachment_counts,
            "chart_data": chart_data,
        }

        await self._emit(
            "completed",
            f"Organized {processed} emails, applied {labels_applied} Gmail labels, saved {attachments_saved} attachments",
            chart_data,
        )
        return summary

    def _walk_parts(self, parts: list[dict]) -> list[dict]:
        collected: list[dict] = []
        for part in parts:
            if part.get("parts"):
                collected.extend(self._walk_parts(part["parts"]))
            else:
                collected.append(part)
        return collected
