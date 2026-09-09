import csv
import io
import os
import secrets
from datetime import datetime, date, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for, flash, Response
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import extract

from config import Config
from models import db, User, Expense, CATEGORIES, CURRENCIES, CURRENCY_SYMBOLS
from mailer import send_reset_code_email, send_verification_code_email
from ai_content import get_daily_quote

EMAIL_RE_SIMPLE_CHECK = lambda s: "@" in s and "." in s.split("@")[-1] and len(s) <= 255


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

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

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

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You've been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/verify-email", methods=["GET", "POST"])
    @limiter.limit("10 per hour")
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
        amount_text = request.form.get("amount", "")
        category = request.form.get("category", "").strip()
        note = request.form.get("note", "").strip()
        date_text = request.form.get("expense_date", "")

        try:
            amount = float(amount_text)
        except ValueError:
            flash("Amount must be a number.", "error")
            return redirect(url_for("index"))

        if amount <= 0:
            flash("Amount must be positive.", "error")
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
            amount=round(amount, 2),
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
            amount_text = request.form.get("amount", "")
            category = request.form.get("category", "").strip()
            note = request.form.get("note", "").strip()
            date_text = request.form.get("expense_date", "")

            try:
                amount = float(amount_text)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                flash("Amount must be a positive number.", "error")
                return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, currency_symbol=currency_symbol)

            if category not in CATEGORIES:
                flash("Please choose a valid category.", "error")
                return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, currency_symbol=currency_symbol)

            try:
                expense.expense_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date.", "error")
                return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, currency_symbol=currency_symbol)

            expense.amount = round(amount, 2)
            expense.category = category
            expense.note = note
            db.session.commit()
            flash("Expense updated.", "success")
            return redirect(url_for("index"))

        return render_template("edit_expense.html", expense=expense, categories=CATEGORIES, currency_symbol=currency_symbol)

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