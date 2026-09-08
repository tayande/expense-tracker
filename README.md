# Expense Tracker

Flask expense tracker with accounts, email-based password reset, and Postgres storage.

## Local setup

1. `python3 -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in `SECRET_KEY` (any random string for local dev).
4. Leave `DATABASE_URL` unset locally — it falls back to a local SQLite file automatically.
5. Leave `MAIL_SUPPRESS_SEND=true` unless you've set up Gmail (see below) — reset codes will print to your terminal instead of emailing.
6. Export the vars from `.env` into your shell, then run: `python3 app.py`
7. Open `http://127.0.0.1:5000`

## Setting up Gmail to actually send reset emails

1. Go to your Google Account → Security → 2-Step Verification (must be turned on).
2. Under "2-Step Verification," find **App passwords**.
3. Generate a new app password (choose "Mail" as the app).
4. Copy the 16-character password Google gives you.
5. Set these environment variables:
   - `MAIL_USERNAME` = your Gmail address
   - `MAIL_PASSWORD` = the 16-character app password (not your normal Gmail password)
   - `MAIL_DEFAULT_SENDER` = same Gmail address
   - `MAIL_SUPPRESS_SEND` = `false`

## Deploying to Render

1. **Create the Postgres database first**: Render dashboard → New → PostgreSQL. Once it's created, copy its "Internal Database URL."
2. **Create the web service**: New → Web Service → connect your repo.
3. Set the **Start Command** to: `gunicorn app:app`
4. Under **Environment**, add:
   - `SECRET_KEY` — generate one locally with `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `DATABASE_URL` — the Postgres URL you copied in step 1
   - `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` — your Gmail credentials
   - `MAIL_SUPPRESS_SEND` — `false`
   - `FLASK_DEBUG` — leave unset or `false`
5. Deploy. Render sets `PORT` automatically; the app already reads it.
6. If `SECRET_KEY` or `DATABASE_URL` is missing, the app will refuse to start and tell you exactly which one — check the deploy logs.

## Running tests

```
pip install pytest
pytest
```