"""Tests for signup, email verification, login, logout and password reset."""
from werkzeug.security import generate_password_hash

from models import db, User
from conftest import get_csrf_token


def signup(client, username="bob", email="bob@example.com", password="password123"):
    return client.post("/signup", data={
        "username": username,
        "email": email,
        "password": password,
        "currency_code": "USD",
    })


# --- Signup and verification ---------------------------------------------

def test_signup_creates_unverified_user_and_sends_code(client, sent_emails):
    response = signup(client)

    assert response.status_code == 302
    user = User.query.filter_by(email="bob@example.com").one()
    assert user.email_verified is False
    assert sent_emails[-1][:2] == ("verify", "bob@example.com")


def test_correct_code_verifies_and_logs_in(client, sent_emails):
    signup(client)
    code = sent_emails[-1][2]

    response = client.post("/verify-email", data={"email": "bob@example.com", "code": code})

    assert response.status_code == 302
    assert User.query.filter_by(email="bob@example.com").one().email_verified is True
    assert client.get("/dashboard").status_code == 200


def test_wrong_code_is_rejected(client, sent_emails):
    signup(client)

    response = client.post("/verify-email", data={"email": "bob@example.com", "code": "000000"})

    assert b"invalid or has expired" in response.data
    assert User.query.filter_by(email="bob@example.com").one().email_verified is False


def test_username_longer_than_80_characters_is_rejected(client):
    response = signup(client, username="u" * 81)

    assert b"80 characters or fewer" in response.data
    assert User.query.count() == 0


def test_username_of_exactly_80_characters_is_accepted(client):
    signup(client, username="u" * 80)

    assert User.query.count() == 1


def test_short_password_is_rejected(client):
    response = signup(client, password="short")

    assert b"at least 8 characters" in response.data
    assert User.query.count() == 0


# --- Login -----------------------------------------------------------------

def test_login_with_correct_password(client, make_user):
    make_user()

    response = client.post("/login", data={"username": "alice", "password": "password123"})

    assert response.status_code == 302
    assert client.get("/dashboard").status_code == 200


def test_login_with_wrong_password_fails(client, make_user):
    make_user()

    response = client.post("/login", data={"username": "alice", "password": "wrong-password"})

    assert b"Invalid username or password" in response.data


def test_unverified_user_cannot_log_in(client, make_user):
    make_user(verified=False)

    response = client.post("/login", data={"username": "alice", "password": "password123"})

    assert "/verify-email" in response.headers["Location"]
    assert client.get("/dashboard").status_code == 302  # bounced to login


# --- Logout (step 5) --------------------------------------------------------

def test_logout_by_plain_link_is_refused(logged_in_client):
    assert logged_in_client.get("/logout").status_code == 405


def test_logout_by_post_logs_out(logged_in_client):
    response = logged_in_client.post("/logout")

    assert response.status_code == 302
    assert logged_in_client.get("/dashboard").status_code == 302


def test_logout_without_csrf_token_is_refused(csrf_app):
    client = csrf_app.test_client()
    user = User(username="alice", email="alice@example.com",
                password_hash=generate_password_hash("password123"), email_verified=True)
    db.session.add(user)
    db.session.commit()
    token = get_csrf_token(client.get("/login").text)
    client.post("/login", data={"username": "alice", "password": "password123", "csrf_token": token})

    assert client.post("/logout").status_code == 400          # no token: refused
    assert client.get("/dashboard").status_code == 200        # still logged in

    token = get_csrf_token(client.get("/dashboard").text)
    assert client.post("/logout", data={"csrf_token": token}).status_code == 302
    assert client.get("/dashboard").status_code == 302        # now logged out


# --- Password reset ----------------------------------------------------------

def test_password_reset_flow(client, make_user, sent_emails):
    make_user()
    client.post("/forgot-password", data={"email": "alice@example.com"})
    kind, _, code = sent_emails[-1]
    assert kind == "reset"

    response = client.post("/reset-password", data={
        "email": "alice@example.com", "code": code, "password": "brand-new-pass",
    })

    assert response.status_code == 302
    login = client.post("/login", data={"username": "alice", "password": "brand-new-pass"})
    assert login.status_code == 302


# --- Code-guessing limit (step 6) ------------------------------------------

def test_sixth_wrong_code_for_same_email_is_blocked(app, client, sent_emails):
    signup(client)
    correct_code = sent_emails[-1][2]

    # Each guess comes from a different IP, like an attacker switching networks
    for i in range(5):
        guess = app.test_client().post(
            "/verify-email",
            data={"email": "bob@example.com", "code": "000000"},
            environ_base={"REMOTE_ADDR": f"10.0.0.{i}"},
        )
        assert guess.status_code == 200

    blocked = app.test_client().post(
        "/verify-email",
        data={"email": "bob@example.com", "code": correct_code},
        environ_base={"REMOTE_ADDR": "10.0.0.99"},
    )
    assert blocked.status_code == 429


def test_code_limit_is_per_email(app, client, make_user, sent_emails):
    # Use up the limit for one email...
    for i in range(5):
        app.test_client().post(
            "/verify-email",
            data={"email": "victim@example.com", "code": "000000"},
            environ_base={"REMOTE_ADDR": f"10.0.1.{i}"},
        )

    # ...another account can still verify normally
    signup(client)
    code = sent_emails[-1][2]
    response = client.post("/verify-email", data={"email": "bob@example.com", "code": code})
    assert response.status_code == 302