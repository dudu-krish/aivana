from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    app_secret: str = "change-me-in-production"
    app_base_url: str = "http://localhost:8001"
    # Full OAuth redirect URI — set this in production (must match Google Console exactly).
    # Example: https://agents.yourcompany.com/api/gmail/callback
    oauth_redirect_uri: str = ""

    google_client_secrets_file: Path = ROOT_DIR / "credentials" / "client_secret.json"
    # Heroku / CI: paste the full Google OAuth JSON (no file mount needed)
    google_client_secrets_json: str = ""

    data_dir: Path = ROOT_DIR / "data"
    tenants_dir: Path = ROOT_DIR / "data" / "tenants"
    db_path: Path = ROOT_DIR / "data" / "agent.db"

    # Legacy demo paths (unused in multi-tenant mode)
    invoices_dir: Path = ROOT_DIR / "data" / "invoices"
    payments_dir: Path = ROOT_DIR / "data" / "payments"
    gmail_attachments_dir: Path = ROOT_DIR / "data" / "gmail_attachments"

    # Telecaller (Twilio) — optional; agent simulates calls when unset
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    # WhatsApp via Twilio — e.g. whatsapp:+14155238886 (sandbox) or your approved sender
    twilio_whatsapp_from: str = ""

    # Mailer (SMTP) — optional; agent simulates sends when unset
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    # Planner LLM — set OPENAI_API_KEY for intelligent routing
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    planner_model: str = "gpt-4o-mini"
    planner_temperature: float = 0.2
    llm_timeout_seconds: int = 60

    # Scraper / file download
    scraper_user_agent: str = "AgentStudio/1.0 (+https://github.com/agent-studio)"
    download_timeout_seconds: int = 60


settings = Settings()


def get_oauth_redirect_uri() -> str:
    if settings.oauth_redirect_uri.strip():
        return settings.oauth_redirect_uri.strip()
    return f"{settings.app_base_url.rstrip('/')}/api/gmail/callback"
