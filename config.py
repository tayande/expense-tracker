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

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", MAIL_USERNAME)
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "false").lower() in ("1", "true", "yes")


class TestConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    MAIL_USERNAME = "test@example.com"
    MAIL_PASSWORD = "testpass"
    MAIL_DEFAULT_SENDER = "test@example.com"
    MAIL_SUPPRESS_SEND = True