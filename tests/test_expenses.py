"""Tests for adding, editing, deleting and exporting expenses."""
import pytest

from app import parse_amount
from models import db, Expense


def add_expense(client, amount="10", category="Food", note="", expense_date="2026-09-01"):
    return client.post("/add", data={
        "amount": amount,
        "category": category,
        "note": note,
        "expense_date": expense_date,
    }, follow_redirects=True)


# --- parse_amount helper (step 3) -------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("10", 10.0),
    ("12.346", 12.35),            # rounded to 2 decimal places
    ("0.01", 0.01),               # smallest allowed amount
    ("9999999999.99", 9999999999.99),
])
def test_parse_amount_accepts_valid_amounts(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", [
    "nan", "NaN", "inf", "-inf", "infinity",   # special float words
    "abc", "", None,                            # not numbers
    "0", "-5", "0.001",                         # zero, negative, rounds to 0
    "1e20", "10000000000",                      # too large
])
def test_parse_amount_rejects_invalid_amounts(text):
    assert parse_amount(text) is None


# --- Adding expenses ---------------------------------------------------------

def test_add_valid_expense(logged_in_client):
    response = add_expense(logged_in_client, amount="25.50", note="Lunch")

    assert b"Expense added" in response.data
    expense = Expense.query.one()
    assert expense.amount == 25.5
    assert expense.note == "Lunch"


@pytest.mark.parametrize("bad_amount", ["nan", "inf", "-5", "0", "abc", "1e20"])
def test_add_rejects_invalid_amount(logged_in_client, bad_amount):
    response = add_expense(logged_in_client, amount=bad_amount)

    assert b"Amount must be a positive number" in response.data
    assert Expense.query.count() == 0


def test_add_rejects_invalid_category(logged_in_client):
    add_expense(logged_in_client, category="Not a category")

    assert Expense.query.count() == 0


def test_add_rejects_note_over_255_characters(logged_in_client):
    response = add_expense(logged_in_client, note="n" * 256)

    assert b"255 characters or fewer" in response.data
    assert Expense.query.count() == 0


def test_add_accepts_note_of_exactly_255_characters(logged_in_client):
    add_expense(logged_in_client, note="n" * 255)

    assert Expense.query.count() == 1


def test_add_requires_login(client):
    response = client.post("/add", data={"amount": "10", "category": "Food"})

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert Expense.query.count() == 0


# --- Editing expenses ----------------------------------------------------------

def test_edit_expense(logged_in_client):
    add_expense(logged_in_client, amount="10")

    logged_in_client.post("/edit/1", data={
        "amount": "7.5", "category": "Transport", "note": "Bus", "expense_date": "2026-09-02",
    })

    expense = db.session.get(Expense, 1)
    assert expense.amount == 7.5
    assert expense.category == "Transport"


@pytest.mark.parametrize("bad_amount", ["nan", "inf", "0"])
def test_edit_with_invalid_amount_keeps_old_value(logged_in_client, bad_amount):
    add_expense(logged_in_client, amount="10")

    response = logged_in_client.post("/edit/1", data={
        "amount": bad_amount, "category": "Food", "expense_date": "2026-09-01",
    })

    assert b"Amount must be a positive number" in response.data
    db.session.expire_all()
    assert db.session.get(Expense, 1).amount == 10.0


def test_edit_rejects_long_note(logged_in_client):
    add_expense(logged_in_client, note="original")

    response = logged_in_client.post("/edit/1", data={
        "amount": "10", "category": "Food", "note": "n" * 256, "expense_date": "2026-09-01",
    })

    assert b"255 characters or fewer" in response.data
    db.session.expire_all()
    assert db.session.get(Expense, 1).note == "original"


# --- Privacy: users can only touch their own expenses ----------------------------

def test_user_cannot_edit_or_delete_someone_elses_expense(app, logged_in_client, make_user):
    add_expense(logged_in_client, amount="10")       # alice's expense, id 1
    logged_in_client.post("/logout")

    make_user(username="mallory", email="mallory@example.com")
    other = app.test_client()
    other.post("/login", data={"username": "mallory", "password": "password123"})

    other.post("/edit/1", data={"amount": "999", "category": "Food", "expense_date": "2026-09-01"})
    other.post("/delete/1")

    db.session.expire_all()
    expense = db.session.get(Expense, 1)
    assert expense is not None
    assert expense.amount == 10.0


# --- Deleting and exporting --------------------------------------------------------

def test_delete_expense(logged_in_client):
    add_expense(logged_in_client)

    logged_in_client.post("/delete/1")

    assert Expense.query.count() == 0


def test_csv_export_contains_expenses(logged_in_client):
    add_expense(logged_in_client, amount="12.5", note="Taxi", category="Transport")

    response = logged_in_client.get("/export.csv")

    assert response.mimetype == "text/csv"
    text = response.get_data(as_text=True)
    assert text.splitlines()[0] == "Date,Category,Amount,Note"
    assert "2026-09-01,Transport,12.50,Taxi" in text