"""YouTube channel OAuth2 — connect creator channels for CreatorOS agents."""

from __future__ import annotations

import json
import os
import secrets

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.config import settings
from app.services.database import (
    clear_youtube_connection,
    consume_oauth_state,
    get_youtube_connection,
    save_oauth_state,
    save_youtube_connection,
)
from app.services.tenant import TenantContext

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _secrets_path():
    raw_json = settings.youtube_client_secrets_json.strip()
    if raw_json:
        path = settings.data_dir / "credentials" / "youtube_client_secret.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(json.loads(raw_json)))
        return path

    yt_path = settings.youtube_client_secrets_file
    if yt_path.exists():
        return yt_path

    raise FileNotFoundError(
        "YouTube OAuth credentials not configured. "
        "On Render, set YOUTUBE_CLIENT_SECRETS_JSON to your YouTube OAuth client JSON "
        "(from credentials/youtube_client_secret.json). "
        "Do not reuse GOOGLE_CLIENT_SECRETS_JSON — YouTube needs its own OAuth client "
        "with https://aivana-65kg.onrender.com/api/youtube/callback in Authorized redirect URIs."
    )


def get_credential_source() -> str:
    if settings.youtube_client_secrets_json.strip():
        return "youtube_client_secrets_json"
    if settings.youtube_client_secrets_file.exists():
        return "youtube_client_secrets_file"
    return "missing"


def get_oauth_client_id() -> str | None:
    try:
        data = json.loads(_secrets_path().read_text())
        web = data.get("web") or data.get("installed") or {}
        return web.get("client_id") or None
    except Exception:
        return None


def create_oauth_flow(redirect_uri: str) -> Flow:
    return Flow.from_client_secrets_file(
        str(_secrets_path()),
        scopes=YOUTUBE_SCOPES,
        redirect_uri=redirect_uri,
    )


def get_authorization_url(user_id: str, redirect_uri: str) -> str:
    flow = create_oauth_flow(redirect_uri)
    state = secrets.token_urlsafe(32)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    if not flow.code_verifier:
        raise RuntimeError("OAuth PKCE verifier was not generated.")
    save_oauth_state(state, user_id, flow.code_verifier, redirect_uri)
    return auth_url


def _fetch_primary_channel(creds: Credentials) -> dict:
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    response = youtube.channels().list(part="snippet,statistics", mine=True, maxResults=1).execute()
    items = response.get("items") or []
    if not items:
        raise ValueError("No YouTube channel found for this Google account.")
    ch = items[0]
    snippet = ch.get("snippet") or {}
    stats = ch.get("statistics") or {}
    return {
        "channel_id": ch.get("id", ""),
        "channel_title": snippet.get("title", "YouTube Channel"),
        "channel_url": f"https://www.youtube.com/channel/{ch.get('id', '')}",
        "subscriber_count": int(stats.get("subscriberCount") or 0),
        "video_count": int(stats.get("videoCount") or 0),
    }


def exchange_code_for_token(code: str, state: str, tenant: TenantContext) -> dict:
    oauth = consume_oauth_state(state)
    if not oauth:
        raise ValueError("Invalid or expired OAuth session. Please try connecting again.")
    user_id, code_verifier, redirect_uri = oauth
    if user_id != tenant.user_id:
        raise ValueError("Invalid or expired OAuth session. Please try connecting again.")
    if not code_verifier or not redirect_uri:
        raise ValueError("OAuth session incomplete. Please try connecting again.")

    disconnect_youtube(tenant)

    flow = create_oauth_flow(redirect_uri)
    flow.fetch_token(code=code, code_verifier=code_verifier)
    creds = flow.credentials
    if not creds or not creds.token:
        raise ValueError("YouTube authorization failed. Please try again.")

    channel = _fetch_primary_channel(creds)
    tenant.ensure_dirs()
    tenant.youtube_token_file.write_text(creds.to_json())
    save_youtube_connection(
        tenant.user_id,
        channel_id=channel["channel_id"],
        channel_title=channel["channel_title"],
        channel_url=channel["channel_url"],
        subscriber_count=channel["subscriber_count"],
    )
    return channel


def load_credentials(tenant: TenantContext) -> Credentials | None:
    token_file = tenant.youtube_token_file
    if not token_file.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_info(json.loads(token_file.read_text()))
    except json.JSONDecodeError:
        return None
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_file.write_text(creds.to_json())
        except Exception:
            return None
    return creds if creds.valid else None


def get_youtube_service(tenant: TenantContext):
    creds = load_credentials(tenant)
    if not creds:
        raise FileNotFoundError(
            "YouTube not connected. Connect your YouTube channel to continue."
        )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def is_youtube_connected(tenant: TenantContext) -> bool:
    return load_credentials(tenant) is not None


def get_connected_youtube_channel(user_id: str) -> dict | None:
    row = get_youtube_connection(user_id)
    if not row:
        return None
    return {
        "channel_id": row["channel_id"],
        "channel_title": row["channel_title"],
        "channel_url": row["channel_url"],
        "subscriber_count": row["subscriber_count"],
    }


def disconnect_youtube(tenant: TenantContext) -> None:
    if tenant.youtube_token_file.exists():
        tenant.youtube_token_file.unlink()
    clear_youtube_connection(tenant.user_id)
