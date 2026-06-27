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
    # YouTube OAuth callback — production: https://aivana-65kg.onrender.com/api/youtube/callback
    youtube_oauth_redirect_uri: str = ""

    google_client_secrets_file: Path = ROOT_DIR / "credentials" / "client_secret.json"
    # Heroku / CI: paste the full Google OAuth JSON (no file mount needed)
    google_client_secrets_json: str = ""

    # Optional separate OAuth client for YouTube (falls back to google_* above)
    youtube_client_secrets_file: Path = ROOT_DIR / "credentials" / "youtube_client_secret.json"
    youtube_client_secrets_json: str = ""

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
    # Comma-separated chat model IDs your API key can call (auto-router + manual pick).
    llm_available_models: str = "gpt-4.1,gpt-4.1-mini,gpt-4.1-nano,gpt-4o,gpt-4o-mini"

    # Scraper / file download
    scraper_user_agent: str = "AgentStudio/1.0 (+https://github.com/agent-studio)"
    download_timeout_seconds: int = 60

    # Organization knowledge base (turbovec)
    kb_db_path: str = "kb_vectors.db"
    kb_turbovec_index_dir: str = "kb_turbovec"
    kb_turbovec_bit_width: int = 4
    kb_embedding_model: str = "text-embedding-3-small"
    kb_database_url: str = ""
    kb_parent_max_chars: int = 1800
    kb_child_max_chars: int = 280
    kb_child_overlap: int = 40
    kb_ask_child_candidates: int = 24
    kb_ask_parent_top_k: int = 5

    # Video embeddings (transcript + visual scene descriptions)
    kb_whisper_model: str = "whisper-1"
    kb_video_frame_interval_sec: float = 30.0
    kb_video_max_frames: int = 20
    kb_video_describe_frames: bool = True
    kb_video_ffmpeg_timeout_seconds: int = 180
    kb_video_whisper_timeout_seconds: int = 300

    # SharePoint (Microsoft Graph) — stream PDFs without download
    sharepoint_graph_base: str = "https://graph.microsoft.com/v1.0"
    sharepoint_site_url: str = ""
    sharepoint_access_token: str = ""

    # LangChain — workflow engine and tool-calling agents
    use_langchain: bool = True

    # Google Gemini / Veo — intro video generation (set GEMINI_API_KEY in .env)
    gemini_api_key: str = ""
    gemini_project_id: str = ""
    veo_model: str = "veo-3.1-fast-generate-preview"
    veo_duration_seconds: int = 8
    veo_aspect_ratio: str = "16:9"

    # CreatorOS — pause production agents for human review (default on)
    content_human_in_loop: bool = True


settings = Settings()


def get_oauth_redirect_uri() -> str:
    if settings.oauth_redirect_uri.strip():
        return settings.oauth_redirect_uri.strip()
    return f"{settings.app_base_url.rstrip('/')}/api/gmail/callback"


def get_youtube_oauth_redirect_uri() -> str:
    if settings.youtube_oauth_redirect_uri.strip():
        return settings.youtube_oauth_redirect_uri.strip()
    base = settings.app_base_url.rstrip("/")
    if base and "localhost" not in base and "127.0.0.1" not in base:
        return f"{base}/api/youtube/callback"
    return ""


def is_production_base_url(url: str) -> bool:
    u = url.strip().lower()
    return bool(u) and "localhost" not in u and "127.0.0.1" not in u


def is_production_host(host: str) -> bool:
    h = host.strip().lower().split(":")[0]
    return bool(h) and "localhost" not in h and "127.0.0.1" not in h


# Production Render deployment — used when env vars are not set yet.
RENDER_APP_URL = "https://aivana-65kg.onrender.com"
