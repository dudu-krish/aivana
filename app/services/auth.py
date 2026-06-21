"""Customer authentication — each buyer gets their own account."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt

from app.services.database import (
    create_session,
    create_user,
    delete_session,
    get_session_user,
    get_user_by_email,
    get_user_by_id,
    get_user_preferences,
    upsert_user_preferences,
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def register_customer(email: str, name: str, password: str, use_case: str = "all") -> dict:
    if get_user_by_email(email):
        raise ValueError("An account with this email already exists")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    user_id = str(uuid.uuid4())
    create_user(user_id, email, name, hash_password(password))
    upsert_user_preferences(user_id, use_case=use_case or "all", onboarding_completed=False)
    token = secrets.token_urlsafe(32)
    create_session(token, user_id)
    user = get_user_by_id(user_id)
    return {"token": token, "user": _user_dict(user)}


def login_customer(email: str, password: str) -> dict:
    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        raise ValueError("Invalid email or password")

    token = secrets.token_urlsafe(32)
    create_session(token, user["id"])
    return {"token": token, "user": _user_dict(user)}


def logout_customer(token: str) -> None:
    delete_session(token)


def resolve_session(token: str | None) -> dict | None:
    if not token:
        return None
    user = get_session_user(token)
    if not user:
        return None
    return _user_dict(user)


_ws_tickets: dict[str, tuple[str, datetime]] = {}


def create_ws_ticket(user_id: str, minutes: int = 15) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    _ws_tickets[token] = (user_id, expires)
    return token


def resolve_ws_ticket(token: str | None) -> dict | None:
    if not token:
        return None
    entry = _ws_tickets.get(token)
    if not entry:
        return None
    user_id, expires = entry
    if datetime.now(timezone.utc) > expires:
        _ws_tickets.pop(token, None)
        return None
    user = get_user_by_id(user_id)
    return _user_dict(user) if user else None


def _user_dict(user) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
    }
