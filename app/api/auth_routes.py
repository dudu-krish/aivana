from __future__ import annotations

from typing import Annotated

from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import SESSION_COOKIE, get_current_user
from app.services.auth import (
    create_ws_ticket,
    login_customer,
    logout_customer,
    register_customer,
    resolve_session,
)
from app.services.database import (
    get_user_preferences,
    record_onboarding_complete,
    record_onboarding_skip,
    upsert_user_preferences,
)
from app.services.gmail_auth import get_connected_gmail_email, is_gmail_connected
from app.services.tenant import TenantContext

router = APIRouter(prefix="/api/auth")

USE_CASES = {"email", "invoices", "support", "all"}


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    use_case: str = "all"


class PreferencesRequest(BaseModel):
    use_case: str | None = None
    onboarding_completed: bool | None = None


class OnboardingEventRequest(BaseModel):
    event: Literal["skip", "complete"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _cookie_secure(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded = request.headers.get("x-forwarded-proto", "")
    return forwarded.split(",")[0].strip() == "https"


def _set_session_cookie(response: Response, token: str, request: Request) -> None:
    secure = _cookie_secure(request)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=60 * 60 * 24 * 30,
        secure=secure,
    )


def _clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=_cookie_secure(request),
    )


@router.post("/register")
async def register(body: RegisterRequest, request: Request, response: Response) -> dict:
    use_case = body.use_case if body.use_case in USE_CASES else "all"
    try:
        result = register_customer(body.email, body.name, body.password, use_case)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _set_session_cookie(response, result["token"], request)
    prefs = get_user_preferences(result["user"]["id"])
    return {"user": result["user"], "preferences": prefs}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict:
    try:
        result = login_customer(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_session_cookie(response, result["token"], request)
    prefs = get_user_preferences(result["user"]["id"])
    return {"user": result["user"], "preferences": prefs}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    if agent_session:
        logout_customer(agent_session)
    _clear_session_cookie(response, request)
    return {"status": "logged_out"}


@router.get("/ws-ticket")
async def ws_ticket(user: Annotated[dict, Depends(get_current_user)]) -> dict[str, str]:
    return {"ticket": create_ws_ticket(user["id"])}


@router.get("/me")
async def get_me(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    tenant = TenantContext(user_id=user["id"], email=user["email"], name=user["name"])
    return {
        "user": user,
        "preferences": get_user_preferences(user["id"]),
        "gmail": {
            "connected": is_gmail_connected(tenant),
            "email": get_connected_gmail_email(user["id"]),
        },
    }


@router.patch("/preferences")
async def update_preferences(
    body: PreferencesRequest,
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    use_case = body.use_case
    if use_case is not None and use_case not in USE_CASES:
        raise HTTPException(status_code=400, detail="Invalid use case")
    prefs = upsert_user_preferences(
        user["id"],
        use_case=use_case,
        onboarding_completed=body.onboarding_completed,
    )
    return {"preferences": prefs}


@router.post("/preferences/onboarding")
async def record_onboarding_event(
    body: OnboardingEventRequest,
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    if body.event == "skip":
        prefs = record_onboarding_skip(user["id"])
    else:
        prefs = record_onboarding_complete(user["id"])
    return {"preferences": prefs}


@router.get("/session")
async def check_session(
    agent_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    user = resolve_session(agent_session)
    return {"authenticated": user is not None, "user": user}
