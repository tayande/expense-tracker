#!/usr/bin/env python3
"""
Expense Tracker CLI.

Usage:
    python cli.py add --amount 25.50 --category food --note "Lunch"
    python cli.py list
    python cli.py list --category food
    python cli.py delete --id 3
    python cli.py summary
"""

import argparse
import sys

from tracker import ExpenseTracker, Expense


def print_table(expenses: list[Expense]) -> None:
    if not expenses:
        print("No expenses found.")
        return
    print(f"{'ID':<4}{'Date':<12}{'Category':<15}{'Amount':<10}Note")
    print("-" * 55)
    for e in expenses:
        print(f"{e.id:<4}{e.date:<12}{e.category:<15}{e.amount:<10.2f}{e.note}")


def main():
    parser = argparse.ArgumentParser(description="Track and review personal expenses.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_p = subparsers.add_parser("add", help="Add a new expense")
    add_p.add_argument("--amount", type=float, required=True)
    add_p.add_argument("--category", type=str, required=True)
    add_p.add_argument("--note", type=str, default="")
    add_p.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (default: today)")

    list_p = subparsers.add_parser("list", help="List expenses")
    list_p.add_argument("--category", type=str, default=None)

    delete_p = subparsers.add_parser("delete", help="Delete an expense by ID")
    delete_p.add_argument("--id", type=int, required=True)

    subparsers.add_parser("summary", help="Show totals by category")

    args = parser.parse_args()
    tracker = ExpenseTracker()

    try:
        if args.command == "add":
            expense = tracker.add(args.amount, args.category, args.note, args.date)
            print(f"Added expense #{expense.id}: {expense.amount} ({expense.category}) on {expense.date}")

        elif args.command == "list":
            print_table(tracker.list(args.category))

        elif args.command == "delete":
            if tracker.delete(args.id):
                print(f"Deleted expense #{args.id}")
            else:
                print(f"No expense found with ID {args.id}", file=sys.stderr)
                sys.exit(1)

        elif args.command == "summary":
            data = tracker.summary()
            print("Totals by category:")
            for cat, amt in data["by_category"].items():
                print(f"  {cat:<15}{amt:.2f}")
            print(f"\nGrand total: {data['total']:.2f}")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()