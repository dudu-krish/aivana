"""Organization knowledge base agent — transparent ingest + ask."""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.services.event_bus import event_bus
from app.services.knowledge_base.service import KnowledgeBaseService
from app.services.tenant import TenantContext

AGENT_ID = "org-knowledge-base"
AGENT_NAME = "Organization Knowledge Base"


class OrganizationKnowledgeBaseAgent(BaseAgent):
    agent_id = AGENT_ID
    agent_name = AGENT_NAME

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant
        self._kb = KnowledgeBaseService(tenant)

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, self.agent_id, self.agent_name, event_type, message, data
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        action = str(kwargs.get("action") or "build").strip().lower()

        if action == "ask":
            question = str(kwargs.get("question") or "").strip()
            if not question:
                await self._emit("error", "Enter a question to search the knowledge base.")
                return {"status": "error", "message": "No question"}
            await self._emit("started", "Searching organization knowledge base…")
            result = await self._kb.ask(
                question,
                collection=kwargs.get("collection"),
                top_k=int(kwargs.get("top_k") or 8),
            )
            if result.get("status") == "error":
                await self._emit("error", result.get("message", "Ask failed"))
                return result
            await self._emit(
                "completed",
                "Answer ready",
                {"result": result, "answer": result.get("answer"), "sources": result.get("sources")},
            )
            return result

        sources = kwargs.get("sources") or []
        if not sources:
            folder = str(kwargs.get("folder_path") or kwargs.get("source") or "").strip()
            if not folder:
                folder = str(kwargs.get("pdf_folder") or ".").strip() or "."
            sources = [{"type": "folder_pdf", "folder": folder}]
        else:
            cleaned: list[dict[str, Any]] = []
            for spec in sources:
                if str(spec.get("type") or "").lower() in ("folder_pdf", "pdf_folder", "folder"):
                    folder = str(spec.get("folder") or spec.get("path") or "").strip()
                    if not folder:
                        folder = str(kwargs.get("folder_path") or ".").strip() or "."
                    cleaned.append({**spec, "type": "folder_pdf", "folder": folder})
                else:
                    cleaned.append(spec)
            sources = cleaned

        await self._emit(
            "started",
            "Building knowledge base — AI reads & indexes; you keep judgment & relationships",
        )

        async def progress(msg: str, data: dict | None = None) -> None:
            await self._emit("progress", msg, data)

        result = await self._kb.build(
            sources,
            collection=kwargs.get("collection"),
            on_progress=progress,
        )
        await self._emit("completed", "Knowledge base build complete", {"result": result})
        return result
