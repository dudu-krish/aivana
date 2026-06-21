from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status

from app.services.auth import resolve_session
from app.services.tenant import TenantContext

SESSION_COOKIE = "agent_session"


async def get_current_user(
    agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    user = resolve_session(agent_session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please sign in to continue",
        )
    return user


async def get_tenant(
    user: Annotated[dict, Depends(get_current_user)],
) -> TenantContext:
    tenant = TenantContext(user_id=user["id"], email=user["email"], name=user["name"])
    tenant.ensure_dirs()
    return tenant
