"""Shared test setup (pytest loads this file automatically).

Important: app.py builds an app as soon as it is imported, and that app
refuses to start without SECRET_KEY / DATABASE_URL. So we set safe test
values in the environment BEFORE importing anything from the project.
"""
import os
import re

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")  # no file on disk
os.environ.setdefault("MAIL_SUPPRESS_SEND", "true")

import pytest
from werkzeug.security import generate_password_hash

import app as app_module
from config import TestConfig
from models import db, User


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    """Keep tests offline and fast: fake the AI quote and capture emails."""
    monkeypatch.setattr(app_module, "get_daily_quote", lambda app: "Test quote")

    sent = []  # every code "emailed" during a test ends up here

    def fake_verification_email(app, to_address, code):
        sent.append(("verify", to_address, code))

    def fake_reset_email(app, to_address, code):
        sent.append(("reset", to_address, code))

    monkeypatch.setattr(app_module, "send_verification_code_email", fake_verification_email)
    monkeypatch.setattr(app_module, "send_reset_code_email", fake_reset_email)
    return sent


@pytest.fixture
def sent_emails(no_external_calls):
    """List of (kind, email, code) tuples sent during the test."""
    return no_external_calls


@pytest.fixture
def app():
    """A fresh app with an empty in-memory database for every test."""
    application = app_module.create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    """Create a user directly in the database (verified by default)."""
    def _make_user(username="alice", email="alice@example.com",
                   password="password123", verified=True):
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            email_verified=verified,
        )
        db.session.add(user)
        db.session.commit()
        return user
    return _make_user


@pytest.fixture
def logged_in_client(client, make_user):
    """A client already logged in as a verified user 'alice'."""
    make_user()
    response = client.post("/login", data={"username": "alice", "password": "password123"})
    assert response.status_code == 302
    return client


@pytest.fixture
def csrf_app():
    """An app with CSRF protection ON, like the live site."""
    class CsrfConfig(TestConfig):
        WTF_CSRF_ENABLED = True

    application = app_module.create_app(CsrfConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


def get_csrf_token(html):
    """Pull the hidden csrf_token value out of a rendered page."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "no CSRF token found on page"
    return match.group(1)