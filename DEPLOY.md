# Deploy Agent Studio for Public Access

This guide gets Agent Studio online so anyone can sign up, connect Gmail, and run workflows.

## Prerequisites

- A domain with HTTPS (required for Gmail OAuth and secure cookies)
- Google Cloud OAuth credentials (Web application type)
- Optional: OpenAI API key (smart planner), Twilio (live calls), SMTP (live email)

## 1. Environment variables

Copy `.env.example` to `.env` and set:

```env
APP_BASE_URL=https://your-domain.com
OAUTH_REDIRECT_URI=https://your-domain.com/api/gmail/callback
APP_SECRET=<long-random-string-at-least-32-chars>
GOOGLE_CLIENT_SECRETS_FILE=credentials/client_secret.json
OPENAI_API_KEY=sk-...
```

Generate a secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 2. Google Cloud OAuth

1. [Google Cloud Console](https://console.cloud.google.com/) → create project
2. Enable **Gmail API**
3. OAuth consent screen → **External** → add scopes:
   - `gmail.readonly`
   - `gmail.modify`
   - `calendar.readonly` (for Gmail Calendar agent)
   - `calendar.events` (for Gmail Calendar agent)
4. Credentials → **OAuth 2.0 Client ID** → **Web application**
5. Authorized redirect URI: `https://your-domain.com/api/gmail/callback`
6. Download JSON → `credentials/client_secret.json`

## 3. Deploy with Docker (recommended)

```bash
docker compose up -d --build
```

Data persists in `./data`. Back up this folder regularly.

Health check: `https://your-domain.com/api/health`

## 4. Deploy on a VPS (manual)

```bash
git clone <your-repo> agent-studio && cd agent-studio
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Put **nginx** or **Caddy** in front with TLS:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 5. Platform options

| Platform | Notes |
|----------|-------|
| **Render (FREE)** | **Recommended for $0 hosting** — see [RENDER.md](RENDER.md) |
| **Heroku** | Paid (~$5/mo Eco) — GitHub Actions CI/CD in [HEROKU.md](HEROKU.md) |
| **Railway / Fly.io / Koyeb** | Free tiers with limits; Docker deploy |
| **AWS EC2 / DigitalOcean** | Docker Compose + Caddy for auto-HTTPS |

Always use a **persistent volume** for `data/` — SQLite and tenant files live there.

## 6. First-time user experience

New users automatically get:

- **Personalized sign-up** — choose goal (email, invoices, support, or all)
- **Interactive tutorial** — 60-second walkthrough of the canvas
- **Starter workflow** — pre-built workflow matched to their goal
- **Welcome banner** — personalized tips on return visits

Users can replay the tour anytime via the **?** button in the top nav or **Restart tutorial** in the profile menu.

## 7. Production checklist

- [ ] `APP_BASE_URL` uses `https://`
- [ ] `APP_SECRET` is unique and long
- [ ] Google OAuth redirect URI matches exactly
- [ ] `data/` directory is backed up
- [ ] `.env` and `credentials/` are **not** committed to git
- [ ] OpenAI / Twilio / SMTP keys set if you want live agent actions

## 8. Verify

1. Open `https://your-domain.com`
2. Create account → tutorial should start
3. Complete tour → starter workflow loads
4. Connect Gmail → scan and label emails
5. Run workflow → logs appear in the right sidebar
