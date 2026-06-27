"""Portable workflow template package schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


TEMPLATE_SCHEMA = "agent-studio/template/v1"


class TemplatePackage(BaseModel):
    schema_version: str = Field(default=TEMPLATE_SCHEMA, alias="schema")
    id: str
    name: str
    task: str = ""
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    agent_configs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    def to_export_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
            "id": self.id,
            "name": self.name,
            "task": self.task,
            "nodes": self.nodes,
            "edges": self.edges,
            "agent_configs": self.agent_configs,
            "meta": self.meta,
        }
