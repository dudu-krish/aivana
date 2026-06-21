# Gmail OAuth — Production Setup

`localhost` only works on **your computer during development**. Customers cannot use it.

## For selling to customers (production)

1. **Deploy Agent Studio** to a server with a real domain and **HTTPS**
   - Examples: Railway, Render, Fly.io, AWS, DigitalOcean, Azure
   - Your app URL: `https://agents.yourcompany.com`

2. **Set environment variables** on the server:
   ```env
   APP_BASE_URL=https://agents.yourcompany.com
   OAUTH_REDIRECT_URI=https://agents.yourcompany.com/api/gmail/callback
   ```

3. **Google Cloud Console** → Credentials → your OAuth client → **Authorized redirect URIs**:
   ```
   https://agents.yourcompany.com/api/gmail/callback
   ```

4. **OAuth consent screen** → Publish app (or add test users while in testing)

5. Customers visit `https://agents.yourcompany.com`, sign up, click **Connect Gmail** — done.

---

## For local development (without localhost)

Use a tunnel so Google can reach your callback:

```powershell
# Terminal 1 — run the app
cd agent
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8001

# Terminal 2 — expose it publicly
ngrok http 8001
```

Copy the ngrok HTTPS URL (e.g. `https://abc123.ngrok-free.app`) into `.env`:

```env
APP_BASE_URL=https://abc123.ngrok-free.app
OAUTH_REDIRECT_URI=https://abc123.ngrok-free.app/api/gmail/callback
```

Add the same `OAUTH_REDIRECT_URI` in Google Cloud Console, restart the server, open the ngrok URL in your browser.

---

## Check your configured redirect URI

While the server is running, visit:

```
http://127.0.0.1:8001/api/gmail/setup
```

Copy the `redirect_uri` value into Google Cloud Console — it must match **exactly**.

---

## Summary

| Who | What they do |
|-----|----------------|
| **You (once)** | Google Cloud project, OAuth credentials, redirect URI on your domain |
| **Each customer** | Sign in → Connect Gmail → click Allow |

Customers never visit Google Cloud Console.
