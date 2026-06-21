# Agent Platform

A multi-tenant agent product — each customer signs up, connects their own Gmail, uploads their own files, and runs agents on their isolated data.

## How it works for customers

1. **Create an account** — email + password sign-up
2. **Connect their Gmail** — OAuth consent links *their* mailbox to *their* account
3. **Upload their data** — invoice/payment CSV or Excel files
4. **Run agents** — reconciliation and email organization run on their data only

Each customer's data lives in a separate tenant folder. Gmail tokens are stored per customer. Activity logs are scoped per session.

## Agents

### Invoice Matcher
Pull data → reconcile invoices & payments → surface only exceptions.

### Gmail Organizer
Connect Gmail → scan emails & attachments → categorize → save to category folders → show charts.

## Quick Start (development)

```powershell
cd agent
python -m venv .venv
.venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

Open **http://127.0.0.1:8000** → create an account → connect Gmail or upload files.

## Product setup (your side)

You run one instance of this app. Customers use it through the web UI.

### Environment (`.env`)

```env
APP_BASE_URL=http://localhost:8000
APP_SECRET=long-random-secret-for-production
GOOGLE_CLIENT_SECRETS_FILE=credentials/client_secret.json
```

Set `APP_BASE_URL` to your production domain when deploying.

See **[DEPLOY.md](DEPLOY.md)** for full public deployment instructions (Docker, HTTPS, OAuth, checklist).

### First-time user experience

New sign-ups choose a goal (email, invoices, support, or all). They get a guided tutorial, a personalized starter workflow, and a welcome banner. Preferences are stored per account in the database.

### Gmail OAuth (one Google Cloud project for your product)

1. [Google Cloud Console](https://console.cloud.google.com/) → create a project
2. Enable **Gmail API**
3. OAuth consent screen → configure for external users
4. Create **OAuth 2.0 Web** credentials (not desktop)
5. Add redirect URI: `{APP_BASE_URL}/api/gmail/callback`
6. Download JSON → `credentials/client_secret.json`

Customers authorize *their own* Gmail through your OAuth app. You never see their password.

## Architecture

```
data/tenants/{customer-id}/
├── invoices/           # their uploaded files
├── payments/
├── gmail_attachments/  # organized output
└── credentials/
    └── gmail_token.json  # their OAuth token
```

## API

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /api/auth/register` | — | Create customer account |
| `POST /api/auth/login` | — | Sign in |
| `GET /api/auth/me` | ✓ | Profile + Gmail status |
| `POST /api/data/invoices/upload` | ✓ | Upload invoice files |
| `POST /api/data/payments/upload` | ✓ | Upload payment files |
| `GET /api/gmail/auth-url` | ✓ | Start Gmail OAuth for this customer |
| `POST /api/agents/invoice-matcher/run` | ✓ | Run reconciliation |
| `POST /api/agents/gmail-organizer/run` | ✓ | Organize their Gmail |
| `WS /api/events/ws` | cookie | Live activity (scoped to customer) |

## Invoice file format

**Invoices:** `invoice_id`, `vendor`, `amount`, `reference`, `date`

**Payments:** `payment_id`, `vendor`, `amount`, `reference`, `date`
