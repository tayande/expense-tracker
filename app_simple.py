import json
import os
from flask import Flask, render_template, request, redirect

app = Flask(__name__)
FILE_NAME = "expenses.json"


def load_expenses():
    if not os.path.exists(FILE_NAME):
        return []
    with open(FILE_NAME, "r") as f:
        return json.load(f)


def save_expenses(expenses):
    with open(FILE_NAME, "w") as f:
        json.dump(expenses, f, indent=2)


@app.route("/")
def index():
    expenses = load_expenses()

    
    totals = {}
    for e in expenses:
        totals[e["category"]] = totals.get(e["category"], 0) + e["amount"]

    return render_template("index_simple.html", expenses=expenses, totals=totals, error=None)


@app.route("/add", methods=["POST"])
def add():
    expenses = load_expenses()

    amount_text = request.form["amount"]
    category = request.form["category"]
    note = request.form.get("note", "")

    # Try to convert the amount to a number. If it fails, show an error
    # instead of crashing the page.
    try:
        amount = float(amount_text)
    except ValueError:
        totals = {}
        return render_template("index_simple.html", expenses=expenses, totals=totals,
                                error="Amount must be a number.")

    if amount <= 0:
        totals = {}
        return render_template("index_simple.html", expenses=expenses, totals=totals,
                                error="Amount must be positive.")

    new_id = len(expenses) + 1
    expenses.append({"id": new_id, "amount": amount, "category": category.lower(), "note": note})
    save_expenses(expenses)

    return redirect("/")


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete(expense_id):
    expenses = load_expenses()
    expenses = [e for e in expenses if e["id"] != expense_id]
    save_expenses(expenses)
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)
