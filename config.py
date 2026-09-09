import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    TESTING = False

    SECRET_KEY = os.environ.get("SECRET_KEY")

    _raw_db_url = os.environ.get("DATABASE_URL")
    if _raw_db_url and _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)
    if not _raw_db_url:
        _raw_db_url = f"sqlite:///{os.path.join(BASE_DIR, 'expenses.db')}"
    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = not DEBUG

    WTF_CSRF_ENABLED = True
    EXPENSES_PER_PAGE = 10
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    RESET_CODE_EXPIRY_MINUTES = 15

    BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
    BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL")
    BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME", "Prism")
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "false").lower() in ("1", "true", "yes")


class TestConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    BREVO_API_KEY = "test-api-key"
    MAIL_SUPPRESS_SEND = True