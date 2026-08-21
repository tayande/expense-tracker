"""
Core expense tracking logic — shared by the CLI (cli.py) and the web app (app.py).
"""

import json
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, date
from typing import Optional

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expenses.json")


@dataclass
class Expense:
    id: int
    amount: float
    category: str
    note: str
    date: str = field(default_factory=lambda: date.today().isoformat())


class ExpenseTracker:
    """Handles loading, saving, and manipulating expenses."""

    def __init__(self, data_file: str = DATA_FILE):
        self.data_file = data_file
        self.expenses: list[Expense] = self._load()

    def _load(self) -> list[Expense]:
        if not os.path.exists(self.data_file):
            return []
        try:
            with open(self.data_file, "r") as f:
                raw = json.load(f)
            return [Expense(**item) for item in raw]
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"Warning: could not read existing data ({e}). Starting fresh.", file=sys.stderr)
            return []

    def _save(self) -> None:
        with open(self.data_file, "w") as f:
            json.dump([asdict(e) for e in self.expenses], f, indent=2)

    def _next_id(self) -> int:
        return max((e.id for e in self.expenses), default=0) + 1

    def add(self, amount: float, category: str, note: str, expense_date: Optional[str] = None) -> Expense:
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        if expense_date:
            try:
                datetime.strptime(expense_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Date must be in YYYY-MM-DD format.")
        else:
            expense_date = date.today().isoformat()

        expense = Expense(
            id=self._next_id(),
            amount=round(amount, 2),
            category=category.strip().lower(),
            note=note.strip(),
            date=expense_date,
        )
        self.expenses.append(expense)
        self._save()
        return expense

    def list(self, category: Optional[str] = None) -> list[Expense]:
        results = self.expenses
        if category:
            results = [e for e in results if e.category == category.strip().lower()]
        return sorted(results, key=lambda e: e.date)

    def delete(self, expense_id: int) -> bool:
        original_len = len(self.expenses)
        self.expenses = [e for e in self.expenses if e.id != expense_id]
        if len(self.expenses) < original_len:
            self._save()
            return True
        return False

    def summary(self) -> dict:
        totals: dict[str, float] = {}
        for e in self.expenses:
            totals[e.category] = round(totals.get(e.category, 0) + e.amount, 2)
        grand_total = round(sum(totals.values()), 2)
        return {"by_category": totals, "total": grand_total}