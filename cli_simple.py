import json
import os
import sys

FILE_NAME = "expenses.json"


def load_expenses():
    """Read expenses from the JSON file. Return an empty list if it doesn't exist yet."""
    if not os.path.exists(FILE_NAME):
        return []
    with open(FILE_NAME, "r") as f:
        return json.load(f)


def save_expenses(expenses):
    """Write the full list of expenses back to the JSON file."""
    with open(FILE_NAME, "w") as f:
        json.dump(expenses, f, indent=2)


def add_expense(amount, category, note):
    """Add a new expense and save it."""
    expenses = load_expenses()

    if amount <= 0:
        print("Error: amount must be positive.")
        return

    # Give the new expense the next available ID (1, 2, 3, ...)
    new_id = len(expenses) + 1

    expense = {
        "id": new_id,
        "amount": amount,
        "category": category.lower(),
        "note": note,
    }
    expenses.append(expense)
    save_expenses(expenses)
    print(f"Added expense #{new_id}: {amount} ({category})")


def list_expenses():
    """Print every expense in a simple table."""
    expenses = load_expenses()

    if not expenses:
        print("No expenses yet.")
        return

    for e in expenses:
        print(f"#{e['id']}  {e['amount']:.2f}  {e['category']}  {e['note']}")


def delete_expense(expense_id):
    """Remove an expense by ID."""
    expenses = load_expenses()
    new_expenses = [e for e in expenses if e["id"] != expense_id]

    if len(new_expenses) == len(expenses):
        print(f"No expense found with ID {expense_id}")
        return

    save_expenses(new_expenses)
    print(f"Deleted expense #{expense_id}")


def show_summary():
    """Print total spending per category."""
    expenses = load_expenses()
    totals = {}

    for e in expenses:
        category = e["category"]
        totals[category] = totals.get(category, 0) + e["amount"]

    if not totals:
        print("No expenses yet.")
        return

    print("Totals by category:")
    for category, amount in totals.items():
        print(f"  {category}: {amount:.2f}")
    print(f"Grand total: {sum(totals.values()):.2f}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python cli_simple.py [add|list|delete|summary] ...")
        return

    command = sys.argv[1]

    if command == "add":
        amount = float(sys.argv[2])
        category = sys.argv[3]
        note = sys.argv[4] if len(sys.argv) > 4 else ""
        add_expense(amount, category, note)

    elif command == "list":
        list_expenses()

    elif command == "delete":
        expense_id = int(sys.argv[2])
        delete_expense(expense_id)

    elif command == "summary":
        show_summary()

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
