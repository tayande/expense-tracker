"""Tests for sending feedback and reading it on the admin dashboard.

TestConfig sets ADMIN_EMAILS = {"admin@example.com"}.
"""
import pytest

from models import db, Expense, Feedback


def send(client, message="Great app!", rating=""):
    return client.post("/feedback", data={"message": message, "rating": rating},
                       follow_redirects=True)


# --- Sending feedback ----------------------------------------------------

def test_feedback_form_shown_on_dashboard(logged_in_client):
    html = logged_in_client.get("/dashboard").get_data(as_text=True)

    assert "Send Feedback" in html
    assert 'name="message"' in html
    assert 'name="rating"' in html


def test_send_feedback_with_rating(logged_in_client):
    response = send(logged_in_client, message="Love the CSV export", rating="5")

    assert b"Thanks for your feedback" in response.data
    feedback = Feedback.query.one()
    assert feedback.message == "Love the CSV export"
    assert feedback.rating == 5
    assert feedback.sender.username == "alice"


def test_send_feedback_without_rating(logged_in_client):
    send(logged_in_client, message="Just text, no stars")

    assert Feedback.query.one().rating is None


def test_message_is_trimmed(logged_in_client):
    send(logged_in_client, message="   spaced out   ")

    assert Feedback.query.one().message == "spaced out"


@pytest.mark.parametrize("message", ["", "    "])
def test_empty_message_is_rejected(logged_in_client, message):
    response = send(logged_in_client, message=message)

    assert b"Please write a message" in response.data
    assert Feedback.query.count() == 0


def test_message_over_2000_characters_is_rejected(logged_in_client):
    response = send(logged_in_client, message="x" * 2001)

    assert b"2000 characters or fewer" in response.data
    assert Feedback.query.count() == 0


def test_message_of_exactly_2000_characters_is_accepted(logged_in_client):
    send(logged_in_client, message="x" * 2000)

    assert Feedback.query.count() == 1


@pytest.mark.parametrize("rating", ["0", "6", "abc", "3.5", "-1"])
def test_invalid_rating_is_rejected(logged_in_client, rating):
    response = send(logged_in_client, rating=rating)

    assert b"rating from 1 to 5" in response.data
    assert Feedback.query.count() == 0


def test_feedback_requires_login(client):
    response = client.post("/feedback", data={"message": "hi"})

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert Feedback.query.count() == 0


def test_feedback_is_rate_limited(logged_in_client):
    for i in range(5):
        send(logged_in_client, message=f"message {i}")

    response = logged_in_client.post("/feedback", data={"message": "one too many"})

    assert response.status_code == 429
    assert Feedback.query.count() == 5


# --- Reading feedback as admin -----------------------------------------------

def login_admin(client, make_user):
    make_user(username="boss", email="admin@example.com")
    client.post("/login", data={"username": "boss", "password": "password123"})


def test_admin_sees_feedback_with_sender_profile(app, client, make_user):
    alice = make_user()
    db.session.add_all([
        Expense(owner_id=alice.id, amount=10, category="Food"),
        Expense(owner_id=alice.id, amount=20, category="Transport"),
        Feedback(user_id=alice.id, rating=4, message="Needs a budget feature"),
    ])
    db.session.commit()
    login_admin(client, make_user)

    html = client.get("/admin").get_data(as_text=True)

    assert "Feedback (1)" in html
    assert "Needs a budget feature" in html
    assert "alice" in html
    assert "alice@example.com" in html
    assert "2 expenses logged" in html
    assert "average 4.0" in html


def test_expense_count_uses_singular_for_one(client, make_user):
    alice = make_user()
    db.session.add_all([
        Expense(owner_id=alice.id, amount=10, category="Food"),
        Feedback(user_id=alice.id, message="hi"),
    ])
    db.session.commit()
    login_admin(client, make_user)

    assert "1 expense logged" in client.get("/admin").get_data(as_text=True)


def test_feedback_shown_newest_first(client, make_user):
    alice = make_user()
    db.session.add_all([
        Feedback(user_id=alice.id, message="first message"),
        Feedback(user_id=alice.id, message="second message"),
    ])
    db.session.commit()
    login_admin(client, make_user)

    html = client.get("/admin").get_data(as_text=True)

    assert html.index("second message") < html.index("first message")


def test_html_in_feedback_is_shown_as_text_not_run(client, make_user):
    alice = make_user()
    db.session.add(Feedback(user_id=alice.id, message="<script>alert('hi')</script>"))
    db.session.commit()
    login_admin(client, make_user)

    html = client.get("/admin").get_data(as_text=True)

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_empty_inbox_message(client, make_user):
    login_admin(client, make_user)

    assert "No feedback yet" in client.get("/admin").get_data(as_text=True)