"""Workflow run context for correlating agent results."""

from __future__ import annotations

import contextvars

current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_run_id", default=None
)
