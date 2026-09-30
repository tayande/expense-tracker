from datetime import datetime, date

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

CATEGORIES = [
    "Food",
    "Transport",
    "Housing",
    "Utilities",
    "Entertainment",
    "Health",
    "Shopping",
    "Savings",
    "Other",
]

CURRENCIES = [
    ("USD", "$", "US Dollar"),
    ("NGN", "₦", "Nigerian Naira"),
    ("EUR", "€", "Euro"),
    ("GBP", "£", "British Pound"),
    ("GHS", "₵", "Ghanaian Cedi"),
    ("KES", "KSh", "Kenyan Shilling"),
    ("ZAR", "R", "South African Rand"),
    ("INR", "₹", "Indian Rupee"),
    ("JPY", "¥", "Japanese Yen"),
    ("CAD", "CA$", "Canadian Dollar"),
    ("AUD", "AU$", "Australian Dollar"),
]

CURRENCY_SYMBOLS = {code: symbol for code, symbol, _ in CURRENCIES}


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reset_code_hash = db.Column(db.String(255), nullable=True)
    reset_code_expires_at = db.Column(db.DateTime, nullable=True)

    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_code_hash = db.Column(db.String(255), nullable=True)
    verification_code_expires_at = db.Column(db.DateTime, nullable=True)

    currency_code = db.Column(db.String(3), default="USD", nullable=False)

    expenses = db.relationship(
        "Expense", backref="owner", lazy=True, cascade="all, delete-orphan"
    )


class Expense(db.Model):
    __tablename__ = "expenses"
    __table_args__ = {"sqlite_autoincrement": True}

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    note = db.Column(db.String(255), default="")
    expense_date = db.Column(db.Date, default=date.today, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Feedback(db.Model):
    """A message a user sends about the platform, shown to admins.

    This is a brand-new table, so db.create_all() creates it on the next
    start-up; the existing users/expenses tables are not touched.
    """
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=True)        # 1-5 stars, or None if skipped
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # feedback.sender gives the User who wrote it (no database change needed)
    sender = db.relationship("User", lazy="joined")