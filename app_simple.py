import json
import os
from flask import Flask, render_template, request, redirect, url_for
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# In production on Render, set a SECRET_KEY environment variable for real security.
# This fallback is only for local testing.
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

EXPENSES_FILE = "expenses.json"
USERS_FILE = "users.json"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, username):
        self.id = username


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


@login_manager.user_loader
def load_user(username):
    users = load_users()
    if username in users:
        return User(username)
    return None


def load_expenses():
    if not os.path.exists(EXPENSES_FILE):
        return []
    with open(EXPENSES_FILE, "r") as f:
        return json.load(f)


def save_expenses(expenses):
    with open(EXPENSES_FILE, "w") as f:
        json.dump(expenses, f, indent=2)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        users = load_users()

        if not username or not password:
            return render_template("signup.html", error="Username and password are required.")
        if username in users:
            return render_template("signup.html", error="That username is already taken.")

        users[username] = {"password_hash": generate_password_hash(password)}
        save_users(users)
        login_user(User(username))
        return redirect(url_for("index"))

    return render_template("signup.html", error=None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        users = load_users()
        user_record = users.get(username)

        if user_record and check_password_hash(user_record["password_hash"], password):
            login_user(User(username))
            return redirect(url_for("index"))

        return render_template("login.html", error="Invalid username or password.")

    return render_template("login.html", error=None)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    expenses = [e for e in load_expenses() if e.get("owner") == current_user.id]

    totals = {}
    for e in expenses:
        totals[e["category"]] = totals.get(e["category"], 0) + e["amount"]

    return render_template(
        "index_simple.html",
        expenses=expenses,
        totals=totals,
        error=None,
        username=current_user.id,
    )


@app.route("/add", methods=["POST"])
@login_required
def add():
    all_expenses = load_expenses()
    user_expenses = [e for e in all_expenses if e.get("owner") == current_user.id]

    amount_text = request.form["amount"]
    category = request.form["category"]
    note = request.form.get("note", "")

    # Try to convert the amount to a number. If it fails, show an error
    # instead of crashing the page.
    try:
        amount = float(amount_text)
    except ValueError:
        totals = {}
        return render_template(
            "index_simple.html", expenses=user_expenses, totals=totals,
            error="Amount must be a number.", username=current_user.id
        )

    if amount <= 0:
        totals = {}
        return render_template(
            "index_simple.html", expenses=user_expenses, totals=totals,
            error="Amount must be positive.", username=current_user.id
        )

    new_id = len(all_expenses) + 1
    all_expenses.append({
        "id": new_id,
        "amount": amount,
        "category": category.lower(),
        "note": note,
        "owner": current_user.id,
    })
    save_expenses(all_expenses)
    return redirect(url_for("index"))


@app.route("/delete/<int:expense_id>", methods=["POST"])
@login_required
def delete(expense_id):
    all_expenses = load_expenses()
    all_expenses = [
        e for e in all_expenses
        if not (e["id"] == expense_id and e.get("owner") == current_user.id)
    ]
    save_expenses(all_expenses)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
