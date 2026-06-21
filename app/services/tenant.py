"""Per-customer isolated storage — each buyer's data stays separate."""

from __future__ import annotations

from pathlib import Path

from app.config import settings


class TenantContext:
    def __init__(self, user_id: str, email: str, name: str) -> None:
        self.user_id = user_id
        self.email = email
        self.name = name
        self.root = settings.tenants_dir / user_id

    def ensure_dirs(self) -> None:
        for path in (
            self.invoices_dir,
            self.payments_dir,
            self.gmail_attachments_dir,
            self.downloads_dir,
            self.scraped_data_dir,
            self.credentials_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def invoices_dir(self) -> Path:
        return self.root / "invoices"

    @property
    def payments_dir(self) -> Path:
        return self.root / "payments"

    @property
    def gmail_attachments_dir(self) -> Path:
        return self.root / "gmail_attachments"

    @property
    def downloads_dir(self) -> Path:
        return self.root / "downloads"

    @property
    def scraped_data_dir(self) -> Path:
        return self.root / "scraped_data"

    @property
    def credentials_dir(self) -> Path:
        return self.root / "credentials"

    @property
    def gmail_token_file(self) -> Path:
        return self.credentials_dir / "gmail_token.json"
