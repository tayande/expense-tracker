#!/usr/bin/env python3
"""
Flask web UI for the Expense Tracker.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser.
"""

from flask import Flask, render_template, request, redirect, url_for, flash

from tracker import ExpenseTracker

app = Flask(__name__)
app.secret_key = "dev-secret-key"  # fine for local/dev use


@app.route("/")
def index():
    tracker = ExpenseTracker()
    category_filter = request.args.get("category") or None
    expenses = tracker.list(category_filter)
    summary = tracker.summary()
    categories = sorted(summary["by_category"].keys())
    return render_template(
        "index.html",
        expenses=expenses,
        summary=summary,
        categories=categories,
        active_category=category_filter or "",
    )


@app.route("/add", methods=["POST"])
def add():
    tracker = ExpenseTracker()
    try:
        amount = float(request.form["amount"])
        category = request.form["category"]
        note = request.form.get("note", "")
        expense_date = request.form.get("date") or None
        expense = tracker.add(amount, category, note, expense_date)
        flash(f"Added expense #{expense.id}: {expense.amount:.2f} ({expense.category})", "success")
    except (ValueError, KeyError) as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("index"))


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete(expense_id):
    tracker = ExpenseTracker()
    if tracker.delete(expense_id):
        flash(f"Deleted expense #{expense_id}", "success")
    else:
        flash(f"No expense found with ID {expense_id}", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)