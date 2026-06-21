"""Gmail OAuth2 — each customer connects their own mailbox."""

from __future__ import annotations

import json
import os
import secrets

# Must be set before oauthlib runs token exchange (fixes "Scope has changed" errors).
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.config import get_oauth_redirect_uri, settings
from app.services.database import (
    clear_gmail_connection,
    consume_oauth_state,
    get_gmail_connection,
    save_gmail_connection,
    save_oauth_state,
)
from app.services.tenant import TenantContext

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

SCOPES = GMAIL_SCOPES + CALENDAR_SCOPES


def _secrets_path():
    raw_json = settings.google_client_secrets_json.strip()
    if raw_json:
        path = settings.data_dir / "credentials" / "client_secret.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            parsed = json.loads(raw_json)
            path.write_text(json.dumps(parsed))
        except json.JSONDecodeError as exc:
            raise FileNotFoundError(
                "GOOGLE_CLIENT_SECRETS_JSON is set but is not valid JSON."
            ) from exc
        return path

    path = settings.google_client_secrets_file
    if not path.exists():
        raise FileNotFoundError(
            f"Gmail OAuth app credentials not found at {path}. "
            "Set up Google Cloud OAuth credentials for your product."
        )
    return path


def create_oauth_flow(redirect_uri: str | None = None) -> Flow:
    uri = redirect_uri or get_oauth_redirect_uri()
    return Flow.from_client_secrets_file(
        str(_secrets_path()),
        scopes=SCOPES,
        redirect_uri=uri,
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


def exchange_code_for_token(code: str, state: str, tenant: TenantContext) -> str:
    oauth = consume_oauth_state(state)
    if not oauth:
        raise ValueError("Invalid or expired OAuth session. Please try connecting again.")
    user_id, code_verifier, redirect_uri = oauth
    if user_id != tenant.user_id:
        raise ValueError("Invalid or expired OAuth session. Please try connecting again.")
    if not code_verifier:
        raise ValueError(
            "OAuth session is missing PKCE verifier. Please try connecting again."
        )
    if not redirect_uri:
        raise ValueError(
            "OAuth session is missing redirect URI. Please try connecting again."
        )

    # Drop any previous token so scope upgrades don't conflict with stored grants.
    disconnect_gmail(tenant)

    flow = create_oauth_flow(redirect_uri)
    try:
        flow.fetch_token(code=code, code_verifier=code_verifier)
    except Exception as exc:
        msg = str(exc)
        if "Scope has changed" not in msg and "scope" not in msg.lower():
            raise
        if not flow.credentials or not flow.credentials.token:
            raise ValueError(
                "Google OAuth failed due to scope mismatch. "
                "In Google Cloud Console, add Gmail and Calendar scopes to your "
                "OAuth consent screen, then click Connect Gmail again."
            ) from exc

    creds = flow.credentials
    if not _credentials_have_scopes(creds, GMAIL_SCOPES):
        raise ValueError(
            "Gmail permissions were not granted. Please try Connect Gmail again "
            "and approve all requested permissions."
        )
    tenant.ensure_dirs()
    tenant.gmail_token_file.write_text(creds.to_json())

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    gmail_email = profile.get("emailAddress", "unknown")
    save_gmail_connection(tenant.user_id, gmail_email)
    return gmail_email


def _credentials_have_scopes(creds: Credentials, required: list[str]) -> bool:
    granted = set(creds.scopes or [])
    return all(scope in granted for scope in required)


def load_credentials(tenant: TenantContext) -> Credentials | None:
    token_file = tenant.gmail_token_file
    if not token_file.exists():
        return None
    try:
        info = json.loads(token_file.read_text())
    except json.JSONDecodeError:
        return None
    creds = Credentials.from_authorized_user_info(info)
    if not creds:
        return None
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_file.write_text(creds.to_json())
        except Exception:
            return None
    return creds if creds.valid else None


def get_gmail_service(tenant: TenantContext):
    creds = load_credentials(tenant)
    if not creds:
        raise FileNotFoundError(
            "Gmail not connected. Connect your own Gmail account to continue."
        )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_calendar_service(tenant: TenantContext):
    creds = load_credentials(tenant)
    if not creds:
        raise FileNotFoundError(
            "Google account not connected. Connect Gmail to access Calendar."
        )
    if not _credentials_have_scopes(creds, CALENDAR_SCOPES):
        raise FileNotFoundError(
            "Calendar access not granted. Disconnect Gmail and connect again to "
            "approve Calendar permissions."
        )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def is_gmail_connected(tenant: TenantContext) -> bool:
    return load_credentials(tenant) is not None


def get_connected_gmail_email(user_id: str) -> str | None:
    row = get_gmail_connection(user_id)
    return row["email"] if row else None


def disconnect_gmail(tenant: TenantContext) -> None:
    if tenant.gmail_token_file.exists():
        tenant.gmail_token_file.unlink()
    clear_gmail_connection(tenant.user_id)
