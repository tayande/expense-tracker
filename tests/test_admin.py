"""Tests for the admin dashboard (/admin).

TestConfig sets ADMIN_EMAILS = {"admin@example.com"}.
"""
from datetime import datetime, timedelta

from models import db, User


def login(client, username, password="password123"):
    return client.post("/login", data={"username": username, "password": password})


def test_admin_can_open_dashboard(client, make_user):
    make_user(username="boss", email="admin@example.com")
    login(client, "boss")

    response = client.get("/admin")

    assert response.status_code == 200
    assert b"Platform overview" in response.data


def test_admin_email_match_ignores_case(client, make_user):
    make_user(username="boss", email="Admin@Example.com")
    login(client, "boss")

    assert client.get("/admin").status_code == 200


def test_regular_user_gets_404(client, make_user):
    make_user()  # alice, not an admin
    login(client, "alice")

    assert client.get("/admin").status_code == 404


def test_logged_out_visitor_is_sent_to_login(client):
    response = client.get("/admin")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_unverified_account_with_admin_email_is_refused(app, make_user):
    # Someone signs up with the admin's address but can't verify it.
    # They can't log in normally, so check is_admin logic via a forced login.
    user = make_user(username="imposter", email="admin@example.com", verified=False)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)   # simulate being logged in anyway
        session["_fresh"] = True

    assert client.get("/admin").status_code == 404


def test_dashboard_shows_correct_counts(client, make_user):
    make_user(username="boss", email="admin@example.com")
    make_user(username="bob", email="bob@example.com")
    make_user(username="carol", email="carol@example.com", verified=False)
    old = make_user(username="dave", email="dave@example.com")
    old.created_at = datetime.utcnow() - timedelta(days=30)   # joined a month ago
    db.session.commit()
    login(client, "boss")

    html = client.get("/admin").get_data(as_text=True)

    def tile(label):
        # The number sits in the stat-value span right before its label
        before = html.split(f'<span class="stat-label">{label}</span>')[0]
        return int(before.rsplit('<span class="stat-value">', 1)[1].split("<")[0])

    assert tile("Total users") == 4
    assert tile("Verified") == 3
    assert tile("Never verified") == 1
    assert tile("Joined in last 7 days") == 3
    assert "carol@example.com" in html          # appears in recent signups


def test_admin_link_only_shown_to_admins(client, make_user):
    make_user()
    login(client, "alice")
    assert b'href="/admin"' not in client.get("/dashboard").data

    client.post("/logout")
    make_user(username="boss", email="admin@example.com")
    login(client, "boss")
    assert b'href="/admin"' in client.get("/dashboard").data