"""Data scraper agent — fetch web pages and extract structured data."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.agents.base import BaseAgent
from app.config import settings
from app.services.event_bus import event_bus
from app.services.tenant import TenantContext

AGENT_ID = "data-scraper"
AGENT_NAME = "Data Scraper"

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_slug(url: str) -> str:
    parsed = urlparse(url)
    slug = parsed.netloc + parsed.path.replace("/", "_")
    slug = _SAFE_NAME_RE.sub("_", slug).strip("_")[:80] or "page"
    return slug


class DataScraperAgent(BaseAgent):
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
        css_selector = str(kwargs.get("css_selector") or "").strip()
        extract_links = bool(kwargs.get("extract_links", True))
        max_links = int(kwargs.get("max_links") or 20)

        if not urls:
            await self._emit("error", "No URLs to scrape. Add URLs in the agent configuration.")
            return {"status": "error", "message": "No URLs"}

        output_dir = Path(kwargs.get("output_dir", self.tenant.scraped_data_dir))
        output_dir.mkdir(parents=True, exist_ok=True)

        await self._emit("started", f"Scraping {len(urls)} URL(s)")

        headers = {"User-Agent": settings.scraper_user_agent}
        timeout = settings.download_timeout_seconds
        results: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            headers=headers, timeout=timeout, follow_redirects=True
        ) as client:
            for url in urls:
                await self._emit("progress", f"Fetching {url}")
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    html = resp.text
                    soup = BeautifulSoup(html, "html.parser")

                    title = (soup.title.string or "").strip() if soup.title else ""
                    if css_selector:
                        nodes = soup.select(css_selector)
                        extracted = [n.get_text(" ", strip=True) for n in nodes]
                    else:
                        for tag in soup(["script", "style", "noscript"]):
                            tag.decompose()
                        extracted = [soup.get_text("\n", strip=True)]

                    links: list[str] = []
                    if extract_links:
                        seen: set[str] = set()
                        for anchor in soup.find_all("a", href=True):
                            href = urljoin(url, anchor["href"])
                            if href.startswith(("http://", "https://")) and href not in seen:
                                seen.add(href)
                                links.append(href)
                            if len(links) >= max_links:
                                break

                    record = {
                        "url": url,
                        "status_code": resp.status_code,
                        "title": title,
                        "text_preview": (extracted[0][:500] if extracted else ""),
                        "extracted_count": len(extracted),
                        "links": links,
                    }
                    slug = _safe_slug(url)
                    out_file = output_dir / f"{slug}.json"
                    out_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
                    record["saved_to"] = str(out_file.relative_to(output_dir))
                    results.append(record)

                    await self._emit(
                        "progress",
                        f"Scraped \"{title[:50] or url}\" → {record['saved_to']}",
                        {"url": url, "title": title},
                    )
                except Exception as exc:
                    await self._emit("error", f"Failed to scrape {url}: {exc}")
                    results.append({"url": url, "status": "error", "detail": str(exc)})

                await asyncio.sleep(0.3)

        ok = sum(1 for r in results if "saved_to" in r)
        summary = f"Scraped {ok}/{len(urls)} page(s)"
        await self._emit("completed", summary, {"results": results})
        return {"status": "completed", "results": results, "output_dir": str(output_dir)}
