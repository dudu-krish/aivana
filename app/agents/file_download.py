"""File download agent — download files from URLs to tenant storage."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from app.agents.base import BaseAgent
from app.config import settings
from app.services.event_bus import event_bus
from app.services.tenant import TenantContext

AGENT_ID = "file-download"
AGENT_NAME = "File Download"

_SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*]')


def _filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    name = Path(path).name
    if name and "." in name:
        return _SAFE_NAME_RE.sub("_", name)[:200]
    return "download.bin"


def _safe_filename(name: str) -> str:
    return _SAFE_NAME_RE.sub("_", name)[:200]


class FileDownloadAgent(BaseAgent):
    agent_id = AGENT_ID
    agent_name = AGENT_NAME

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, AGENT_ID, AGENT_NAME, event_type, message, data
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        raw_urls = kwargs.get("urls") or []
        urls = [str(u).strip() for u in raw_urls if str(u).strip()]
        custom_names = kwargs.get("filenames") or []

        if not urls:
            await self._emit("error", "No URLs to download. Add URLs in the agent configuration.")
            return {"status": "error", "message": "No URLs"}

        output_dir = Path(kwargs.get("output_dir", self.tenant.downloads_dir))
        output_dir.mkdir(parents=True, exist_ok=True)

        await self._emit("started", f"Downloading {len(urls)} file(s)")

        headers = {"User-Agent": settings.scraper_user_agent}
        timeout = settings.download_timeout_seconds
        results: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            headers=headers, timeout=timeout, follow_redirects=True
        ) as client:
            for idx, url in enumerate(urls):
                filename = _safe_filename(
                    str(custom_names[idx]).strip()
                    if idx < len(custom_names) and str(custom_names[idx]).strip()
                    else _filename_from_url(url)
                )
                dest = output_dir / filename
                if dest.exists():
                    stem, suffix = dest.stem, dest.suffix
                    dest = output_dir / f"{stem}_{idx}{suffix}"

                await self._emit("progress", f"Downloading {url}")
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    dest.write_bytes(resp.content)
                    size_kb = len(resp.content) / 1024
                    record = {
                        "url": url,
                        "filename": dest.name,
                        "path": str(dest.relative_to(output_dir)),
                        "size_bytes": len(resp.content),
                        "content_type": resp.headers.get("content-type", ""),
                    }
                    results.append(record)
                    await self._emit(
                        "progress",
                        f"Saved {dest.name} ({size_kb:.1f} KB)",
                        record,
                    )
                except Exception as exc:
                    await self._emit("error", f"Download failed for {url}: {exc}")
                    results.append({"url": url, "status": "error", "detail": str(exc)})

                await asyncio.sleep(0.2)

        ok = sum(1 for r in results if "filename" in r)
        summary = f"Downloaded {ok}/{len(urls)} file(s) to {output_dir.name}/"
        await self._emit("completed", summary, {"results": results})
        return {"status": "completed", "results": results, "output_dir": str(output_dir)}
