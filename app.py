import csv
import io
import math
import os
import secrets
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash, Response, abort
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import extract, func

from config import Config
from models import db, User, Expense, Feedback, CATEGORIES, CURRENCIES, CURRENCY_SYMBOLS
from mailer import send_reset_code_email, send_verification_code_email
from ai_content import get_daily_quote

EMAIL_RE_SIMPLE_CHECK = lambda s: "@" in s and "." in s.split("@")[-1] and len(s) <= 255

# Maximum text lengths. These MUST match the column sizes in models.py
# (User.username is String(80), Expense.note is String(255)). Postgres refuses
# longer values and the page would crash with a 500 error, so we check first.
MAX_USERNAME_LENGTH = 80
MAX_NOTE_LENGTH = 255

# Feedback messages are stored as Text (no hard database limit), but we cap
# them so one message can't be enormous.
MAX_FEEDBACK_LENGTH = 2000

# Largest amount we accept. Keeps values sane and fits a Numeric(12, 2) column
# if we switch the database type later.
MAX_AMOUNT = 9_999_999_999.99


def parse_amount(text):
    """Turn the amount typed into the form into a clean number.

    Returns the amount rounded to 2 decimal places, or None if the input
    isn't a valid positive amount.
    """
    try:
        amount = float(text)
    except (TypeError, ValueError):
        # Not a number at all, e.g. "abc" or an empty box
        return None

    # float() also accepts the words "nan", "inf" and "infinity".
    # Those would crash the insert (SQLite) or poison every total (Postgres),
    # so reject anything that isn't a normal, finite number.
    if not math.isfinite(amount):
        return None

    # Round first, so something like 0.001 (which becomes 0.00) is rejected below
    amount = round(amount, 2)
    if amount <= 0 or amount > MAX_AMOUNT:
        return None

    return amount


def issue_verification_code(app, user):
    code = f"{secrets.randbelow(1000000):06d}"
    user.verification_code_hash = generate_password_hash(code)
    user.verification_code_expires_at = datetime.utcnow() + timedelta(
        minutes=app.config["RESET_CODE_EXPIRY_MINUTES"]
    )
    db.session.commit()
    send_verification_code_email(app, user.email, code)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        if app.config.get("DEBUG"):
            app.config["SECRET_KEY"] = "dev-only-insecure-key-do-not-deploy-with-this"
        else:
            raise RuntimeError(
                "SECRET_KEY environment variable is not set. "
                "Generate one and set it in your hosting provider's environment variables."
            )

    if not app.config.get("TESTING") and not app.config.get("DEBUG") and not os.environ.get("DATABASE_URL"):
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Without it, this app would silently use a local SQLite file that "
            "does not persist on most hosting platforms. Set DATABASE_URL to your "
            "Postgres connection string before deploying."
        )

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "login"
    login_manager.login_message = "Please log in to continue."

    CSRFProtect(app)

    limiter = Limiter(
        get_remote_address,
        app=app,
        storage_uri=app.config.get("RATELIMIT_STORAGE_URI", "memory://"),
        default_limits=[],
    )

    # --- Per-account limit on code guesses ---
    # The per-IP limits below can be dodged by switching networks, so we also
    # count failed attempts per EMAIL ADDRESS. 5 wrong guesses per 15 minutes
    # (the code's lifetime) out of 1,000,000 possible codes makes guessing hopeless.

    def email_from_form():
        """Rate-limit key: the email typed into the form, normalised."""
        return "email:" + request.form.get("email", "").strip().lower()

    def attempt_failed(response):
        """Only count failed attempts. A correct code redirects (302);
        a wrong one re-renders the form (200)."""
        return response.status_code != 302

    code_guess_limit = limiter.limit(
        "5 per 15 minutes",
        key_func=email_from_form,
        methods=["POST"],       # only form submissions, not loading the page
        deduct_when=attempt_failed,
    )

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ---------------------------------------------------------------
    # Admin access
    # ---------------------------------------------------------------

    def is_admin(user):
        """True if this user may open the admin dashboard.

        The email must be listed in ADMIN_EMAILS *and* verified. The
        verification check matters: without it, someone could sign up
        with the admin's email address (before the admin does) and get in
        without ever proving they own that inbox.
        """
        return (
            user.is_authenticated
            and user.email_verified
            and user.email.lower() in app.config["ADMIN_EMAILS"]
        )

    def admin_required(view):
        """Like @login_required, but also requires an admin.

        Non-admins get a plain 404 "Page not found", so the admin page
        doesn't even reveal that it exists.
        """
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not is_admin(current_user):
                abort(404)
            return view(*args, **kwargs)
        return wrapped

    @app.context_processor
    def inject_admin_flag():
        """Make `is_admin` available in every template (for the nav link)."""
        return {"is_admin": is_admin(current_user)}

    # ---------------------------------------------------------------
    # Public landing page
    # ---------------------------------------------------------------

    @app.route("/")
    def landing():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        quote = get_daily_quote(app)
        return render_template("landing.html", quote=quote)

    # ---------------------------------------------------------------
    # Auth
    # ---------------------------------------------------------------

    @app.route("/signup", methods=["GET", "POST"])
    @limiter.limit("10 per minute")
    def signup():
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            currency_code = request.form.get("currency_code", "USD")

            if not username or not email or not password:
                flash("All fields are required.", "error")
                return render_template("signup.html", currencies=CURRENCIES)

            if len(username) > MAX_USERNAME_LENGTH:
                flash(f"Username must be {MAX_USERNAME_LENGTH} characters or fewer.", "error")
                return render_template("signup.html", currencies=CURRENCIES)

            if not EMAIL_RE_SIMPLE_CHECK(email):
                flash("Please enter a valid email address.", "error")
                return render_template("signup.html", currencies=CURRENCIES)

            if len(password) < 8:
                flash("Password must be at least 8 characters.", "error")
                return render_template("signup.html", currencies=CURRENCIES)

            if currency_code not in CURRENCY_SYMBOLS:
                flash("Please choose a valid currency.", "error")
                return render_template("signup.html", currencies=CURRENCIES)

            existing_email_user = User.query.filter_by(email=email).first()
            if existing_email_user:
                if existing_email_user.email_verified:
                    flash("An account with that email already exists. Try logging in.", "error")
                    return render_template("signup.html", currencies=CURRENCIES)
                else:
                    try:
                        issue_verification_code(app, existing_email_user)
                    except Exception:
                        flash("We couldn't send the email right now. Please try again shortly.", "error")
                        return render_template("signup.html", currencies=CURRENCIES)
                    flash("We found a pending signup for this email — we've resent your verification code.", "success")
                    return redirect(url_for("verify_email", email=email))

            if User.query.filter_by(username=username).first():
                flash("That username is already taken.", "error")
                return render_template("signup.html", currencies=CURRENCIES)

            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                email_verified=False,
                currency_code=currency_code,
            )
            db.session.add(user)
            db.session.commit()

            try:
                issue_verification_code(app, user)
            except Exception:
                flash("Account created, but we couldn't send a verification email. Use 'Resend code' on the next page.", "error")

            return redirect(url_for("verify_email", email=email))

        return render_template("signup.html", currencies=CURRENCIES)

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("10 per minute")
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            remember = bool(request.form.get("remember"))

            user = User.query.filter_by(username=username).first()

            if user and check_password_hash(user.password_hash, password):
                if not user.email_verified:
                    flash("Please verify your email before logging in.", "error")
                    return redirect(url_for("verify_email", email=user.email))

                login_user(user, remember=remember)
                flash(f"Welcome back, {user.username}.", "success")
                return redirect(url_for("index"))

            flash("Invalid username or password.", "error")
            return render_template("login.html")

        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        flash("You've been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/verify-email", methods=["GET", "POST"])
    @limiter.limit("10 per hour")
    @code_guess_limit
    def verify_email():
        prefill_email = request.args.get("email", "")

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            code = request.form.get("code", "").strip()

            user = User.query.filter_by(email=email).first()

            valid = (
                user
                and not user.email_verified
                and user.verification_code_hash
                and user.verification_code_expires_at
                and user.verification_code_expires_at > datetime.utcnow()
                and check_password_hash(user.verification_code_hash, code)
            )

            if not valid:
                flash("That code is invalid or has expired.", "error")
                return render_template("verify_email.html", prefill_email=email)

            user.email_verified = True
            user.verification_code_hash = None
            user.verification_code_expires_at = None
            db.session.commit()

            login_user(user)
            flash("Email verified. Welcome!", "success")
            return redirect(url_for("index"))

        return render_template("verify_email.html", prefill_email=prefill_email)

    @app.route("/resend-verification", methods=["GET", "POST"])
    @limiter.limit("5 per hour")
    def resend_verification():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = User.query.filter_by(email=email).first()

            if user and not user.email_verified:
                try:
                    issue_verification_code(app, user)
                except Exception:
                    flash("We couldn't send the email right now. Please try again shortly.", "error")
                    return render_template("resend_verification.html")

            flash("If that email has a pending signup, a new code has been sent.", "success")
            return redirect(url_for("verify_email", email=email))

        return render_template("resend_verification.html")

    @app.route("/forgot-password", methods=["GET", "POST"])
    @limiter.limit("5 per hour")
    def forgot_password():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = User.query.filter_by(email=email).first()

            if user:
                code = f"{secrets.randbelow(1000000):06d}"
                user.reset_code_hash = generate_password_hash(code)
                user.reset_code_expires_at = datetime.utcnow() + timedelta(
                    minutes=app.config["RESET_CODE_EXPIRY_MINUTES"]
                )
                db.session.commit()
                try:
                    send_reset_code_email(app, user.email, code)
                except Exception:
                    flash("We couldn't send the email right now. Please try again shortly.", "error")
                    return render_template("forgot_password.html")

            flash("If that email has an account, a reset code has been sent.", "success")
            return redirect(url_for("reset_password", email=email))

        return render_template("forgot_password.html")

    @app.route("/reset-password", methods=["GET", "POST"])
    @limiter.limit("10 per hour")
    @code_guess_limit
    def reset_password():
        prefill_email = request.args.get("email", "")

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            code = request.form.get("code", "").strip()
            new_password = request.form.get("password", "")

            user = User.query.filter_by(email=email).first()

            valid = (
                user
                and user.reset_code_hash
                and user.reset_code_expires_at
                and user.reset_code_expires_at > datetime.utcnow()
                and check_password_hash(user.reset_code_hash, code)
            )

            if not valid:
                flash("That code is invalid or has expired.", "error")
                return render_template("reset_password.html", prefill_email=email)

            if len(new_password) < 8:
                flash("Password must be at least 8 characters.", "error")
                return render_template("reset_password.html", prefill_email=email)

            user.password_hash = generate_password_hash(new_password)
            user.reset_code_hash = None
            user.reset_code_expires_at = None
            db.session.commit()

            flash("Password updated. You can log in now.", "success")
            return redirect(url_for("login"))

        return render_template("reset_password.html", prefill_email=prefill_email)

    # ---------------------------------------------------------------
    # Expenses
    # ---------------------------------------------------------------

    @app.route("/dashboard")
    @login_required
    def index():
        page = request.args.get("page", 1, type=int)
        month_filter = request.args.get("month", "")
        category_filter = request.args.get("category", "")

        query = Expense.query.filter_by(owner_id=current_user.id)

        if month_filter:
            try:
                year, month = (int(x) for x in month_filter.split("-"))
                query = query.filter(
                    extract("year", Expense.expense_date) == year,
                    extract("month", Expense.expense_date) == month,
                )
            except ValueError:
                month_filter = ""

        if category_filter:
            query = query.filter_by(category=category_filter)

        query = query.order_by(Expense.expense_date.desc(), Expense.id.desc())

        pagination = query.paginate(
            page=page, per_page=app.config["EXPENSES_PER_PAGE"], error_out=False
        )
        expenses = pagination.items

        totals = {}
        for e in query.all():
            totals[e.category] = totals.get(e.category, 0) + e.amount
        grand_total = sum(totals.values())

        all_dates = [
            d[0] for d in
            db.session.query(Expense.expense_date).filter_by(owner_id=current_user.id).distinct()
        ]
        available_months = sorted({d.strftime("%Y-%m") for d in all_dates}, reverse=True)
        currency_symbol = CURRENCY_SYMBOLS.get(current_user.currency_code, "$")

        return render_template(
            "index.html",
            expenses=expenses,
            pagination=pagination,
            totals=totals,
            grand_total=grand_total,
            categories=CATEGORIES,
            available_months=available_months,
            selected_month=month_filter,
            selected_category=category_filter,
            today=date.today().isoformat(),
            currency_symbol=currency_symbol,
        )

    @app.route("/add", methods=["POST"])
    @login_required
    def add():
        category = request.form.get("category", "").strip()
        note = request.form.get("note", "").strip()
        date_text = request.form.get("expense_date", "")

        # parse_amount rejects text, zero/negative numbers, "nan"/"inf" and huge values
        amount = parse_amount(request.form.get("amount", ""))
        if amount is None:
            flash("Amount must be a positive number (up to 9,999,999,999.99).", "error")
            return redirect(url_for("index"))

        # The browser's maxlength can be bypassed, so check on the server too
        if len(note) > MAX_NOTE_LENGTH:
            flash(f"Note must be {MAX_NOTE_LENGTH} characters or fewer.", "error")
            return redirect(url_for("index"))

        if category not in CATEGORIES:
            flash("Please choose a valid category.", "error")
            return redirect(url_for("index"))

        try:
            expense_date = datetime.strptime(date_text, "%Y-%m-%d").date() if date_text else date.today()
        except ValueError:
            flash("Invalid date.", "error")
            return redirect(url_for("index"))

        expense = Expense(
            owner_id=current_user.id,
            amount=amount,
            category=category,
            note=note,
            expense_date=expense_date,
        )
        db.session.add(expense)
        db.session.commit()
        flash("Expense added.", "success")
        return redirect(url_for("index"))

    @app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
    @login_required
    def edit(expense_id):
        expense = Expense.query.filter_by(id=expense_id, owner_id=current_user.id).first()
        if not expense:
            flash("Expense not found.", "error")
            return redirect(url_for("index"))

        currency_symbol = CURRENCY_SYMBOLS.get(current_user.currency_code, "$")

        if request.method == "POST":
            category = request.form.get("category", "").strip()
            note = request.form.get("note", "").strip()
            date_text = request.form.get("expense_date", "")

            # Same validation as when adding an expense
            amount = parse_amount(request.form.get("amount", ""))
            if amount is None:
                flash("Amount must be a positive number (up to 9,999,999,999.99).", "error")
                return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, currency_symbol=currency_symbol)

            if len(note) > MAX_NOTE_LENGTH:
                flash(f"Note must be {MAX_NOTE_LENGTH} characters or fewer.", "error")
                return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, currency_symbol=currency_symbol)

            if category not in CATEGORIES:
                flash("Please choose a valid category.", "error")
                return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, currency_symbol=currency_symbol)

            try:
                expense.expense_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date.", "error")
                return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, currency_symbol=currency_symbol)

            expense.amount = amount
            expense.category = category
            expense.note = note
            db.session.commit()
            flash("Expense updated.", "success")
            return redirect(url_for("index"))

        return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, currency_symbol=currency_symbol)

    # ---------------------------------------------------------------
    # Feedback
    # ---------------------------------------------------------------

    @app.route("/feedback", methods=["POST"])
    @login_required
    @limiter.limit("5 per hour")   # stops one person flooding the inbox
    def send_feedback():
        message = request.form.get("message", "").strip()
        rating_text = request.form.get("rating", "")

        if not message:
            flash("Please write a message before sending feedback.", "error")
            return redirect(url_for("index"))

        if len(message) > MAX_FEEDBACK_LENGTH:
            flash(f"Feedback must be {MAX_FEEDBACK_LENGTH} characters or fewer.", "error")
            return redirect(url_for("index"))

        # The star rating is optional: empty means "no rating"
        rating = None
        if rating_text:
            if rating_text not in {"1", "2", "3", "4", "5"}:
                flash("Please choose a rating from 1 to 5 stars.", "error")
                return redirect(url_for("index"))
            rating = int(rating_text)

        db.session.add(Feedback(user_id=current_user.id, rating=rating, message=message))
        db.session.commit()
        flash("Thanks for your feedback!", "success")
        return redirect(url_for("index"))

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            currency_code = request.form.get("currency_code", "")
            if currency_code not in CURRENCY_SYMBOLS:
                flash("Please choose a valid currency.", "error")
                return render_template("settings.html", currencies=CURRENCIES)

            current_user.currency_code = currency_code
            db.session.commit()
            flash("Settings updated.", "success")
            return redirect(url_for("settings"))

        return render_template("settings.html", currencies=CURRENCIES)

    @app.route("/delete/<int:expense_id>", methods=["POST"])
    @login_required
    def delete(expense_id):
        expense = Expense.query.filter_by(id=expense_id, owner_id=current_user.id).first()
        if expense:
            db.session.delete(expense)
            db.session.commit()
            flash("Expense deleted.", "success")
        else:
            flash("Expense not found.", "error")
        return redirect(url_for("index"))

    @app.route("/export.csv")
    @login_required
    def export_csv():
        expenses = (
            Expense.query.filter_by(owner_id=current_user.id)
            .order_by(Expense.expense_date.desc())
            .all()
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Date", "Category", "Amount", "Note"])
        for e in expenses:
            writer.writerow([e.expense_date.isoformat(), e.category, f"{e.amount:.2f}", e.note])

        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=expenses_{current_user.username}.csv"},
        )

    # ---------------------------------------------------------------
    # Admin dashboard
    # ---------------------------------------------------------------

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        week_ago = datetime.utcnow() - timedelta(days=7)

        total_users = User.query.count()
        verified_users = User.query.filter_by(email_verified=True).count()
        stats = {
            "total_users": total_users,
            "verified_users": verified_users,
            # Signed up but never entered their email code
            "unverified_users": total_users - verified_users,
            "new_this_week": User.query.filter(User.created_at >= week_ago).count(),
        }

        recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()

        # --- Feedback inbox (newest first) ---
        feedback_list = (
            Feedback.query.order_by(Feedback.created_at.desc(), Feedback.id.desc())
            .limit(100)
            .all()
        )
        feedback_total = Feedback.query.count()
        average_rating = db.session.query(func.avg(Feedback.rating)).scalar()  # ignores "no rating"

        # How many expenses each sender has logged, fetched in ONE query
        # instead of one query per feedback item
        sender_ids = {f.user_id for f in feedback_list}
        expense_counts = dict(
            db.session.query(Expense.owner_id, func.count(Expense.id))
            .filter(Expense.owner_id.in_(sender_ids))
            .group_by(Expense.owner_id)
            .all()
        ) if sender_ids else {}

        return render_template(
            "admin.html",
            stats=stats,
            recent_users=recent_users,
            feedback_list=feedback_list,
            feedback_total=feedback_total,
            average_rating=average_rating,
            expense_counts=expense_counts,
        )

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Page not found."), 404

    @app.errorhandler(429)
    def rate_limited(e):
        return render_template(
            "error.html", code=429, message="Too many attempts. Please wait a moment and try again."
        ), 429

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template("error.html", code=500, message="Something went wrong on our end."), 500

    return app


app = create_app()

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    app.run(debug=app.config["DEBUG"], host=host, port=port)