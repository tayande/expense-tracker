# Prism — Expense Tracker

A Flask expense tracker with user accounts, email verification, password reset
by emailed code, per-user currency, CSV export, and a daily AI-generated money
quote on the landing page. Users can send feedback with an optional star
rating, upload a profile photo, and admins get a dashboard with user stats
and the feedback inbox.
Uses Postgres in production and SQLite locally.

## Local setup

1. Create and activate a virtual environment, then install dependencies:

   ```bash
   python3 -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`. For local development you only need:
   - `SECRET_KEY` — any random string
   - `FLASK_DEBUG=true` — already set in the example
   - `MAIL_SUPPRESS_SEND=true` — already set; verification and reset codes are
     printed in your terminal instead of emailed

   Leave `DATABASE_URL` empty — the app then uses a local SQLite file
   (`expenses.db`) automatically.

3. Load the variables into your shell. The app reads real environment
   variables; it does not read `.env` by itself.

   ```bash
   # macOS / Linux
   set -a; source .env; set +a

   # Windows PowerShell
   Get-Content .env | Where-Object { $_ -match '=' } | ForEach-Object {
       $name, $value = $_ -split '=', 2
       Set-Item "env:$name" $value
   }
   ```

4. Run the app and open http://127.0.0.1:5000

   ```bash
   python3 app.py
   ```

## Environment variables

| Variable | Required | What it does |
|---|---|---|
| `SECRET_KEY` | In production | Signs session cookies. The app refuses to start without it unless `FLASK_DEBUG` is on. |
| `DATABASE_URL` | In production | Postgres connection string. Unset = local SQLite. The app refuses to start in production without it. |
| `FLASK_DEBUG` | No | `true` for local development only. Never enable it on a live server. |
| `BREVO_API_KEY` | To send email | API key from your Brevo account. |
| `BREVO_SENDER_EMAIL` | To send email | The "from" address. Must be a sender verified in Brevo. |
| `BREVO_SENDER_NAME` | No | Display name on emails. Defaults to `Prism`. |
| `MAIL_SUPPRESS_SEND` | No | `true` prints emails to the terminal instead of sending them. |
| `ANTHROPIC_API_KEY` | No | Enables the AI-generated quote on the landing page. Without it, a built-in quote is shown. |
| `AI_QUOTE_CACHE_MINUTES` | No | How long one generated quote is reused. Defaults to `60`. |
| `ADMIN_EMAILS` | No | Comma-separated emails allowed into the admin dashboard at `/admin`. The account must exist and be verified. |

## Setting up Brevo to send emails

Emails (verification and password-reset codes) are sent through
[Brevo](https://www.brevo.com)'s API.

1. Create a free Brevo account.
2. Add and verify the address you'll send from (Brevo lists these under
   **Senders**). Brevo rejects emails from unverified senders.
3. Create an API key in the **SMTP & API** section of your Brevo settings.
4. Set the environment variables:
   - `BREVO_API_KEY` = the key from step 3
   - `BREVO_SENDER_EMAIL` = the verified address from step 2
   - `MAIL_SUPPRESS_SEND` = `false`

Tip: codes sometimes land in spam at first. The emails remind users to check
their spam folder.

## Deploying to Render

1. **Create the Postgres database first**: Render dashboard → New → PostgreSQL.
   Once it's created, copy its **Internal Database URL**.
2. **Create the web service**: New → Web Service → connect this repo.
   The start command comes from `Procfile` (`gunicorn app:app`); if Render asks,
   enter that command.
3. Under **Environment**, add:
   - `SECRET_KEY` — generate one with
     `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `DATABASE_URL` — the Postgres URL from step 1
   - `BREVO_API_KEY`, `BREVO_SENDER_EMAIL` (and optionally `BREVO_SENDER_NAME`)
   - `MAIL_SUPPRESS_SEND` — `false`
   - `ANTHROPIC_API_KEY` — optional, for AI quotes
   - `ADMIN_EMAILS` — your own account's email, to unlock `/admin`
   - Leave `FLASK_DEBUG` unset
4. Deploy. Render sets `PORT` automatically and the app reads it.
5. If `SECRET_KEY` or `DATABASE_URL` is missing, the app refuses to start and
   says which one — check the deploy logs.

## Security notes

- Passwords and emailed codes are stored only as hashes.
- All forms (including logout) are protected against CSRF.
- Login, signup and code pages are rate-limited per IP address, and wrong
  verification/reset codes are limited to 5 per 15 minutes per email address.
- Profile photos are re-encoded as small JPEGs (which strips hidden data such
  as GPS location), capped at 5 MB per upload, and only visible to their owner
  and admins.
- Never commit `.env`, `venv/` or database files — `.gitignore` covers them.

## Command-line version

`cli_simple.py` is the original command-line tracker. It stores expenses in a
local `expenses.json` file (created automatically, ignored by Git) and is
separate from the web app.

## Running tests

```bash
pip install pytest
pytest
```