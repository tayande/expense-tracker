import smtplib
from email.mime.text import MIMEText


def send_email(app, to_address, subject, body):
    if app.config.get("MAIL_SUPPRESS_SEND"):
        print(f"[MAIL SUPPRESSED] To: {to_address}\nSubject: {subject}\n{body}")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = app.config["MAIL_DEFAULT_SENDER"]
    msg["To"] = to_address

    with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]) as server:
        server.starttls()
        server.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
        server.sendmail(app.config["MAIL_DEFAULT_SENDER"], [to_address], msg.as_string())


def send_reset_code_email(app, to_address, code):
    subject = "Your Expense Tracker password reset code"
    body = (
        f"Your password reset code is: {code}\n\n"
        "This code expires in 15 minutes. If you didn't request this, you can ignore this email.\n\n"
        "Don't see this email in your inbox? Check your spam or junk folder."
    )
    send_email(app, to_address, subject, body)


def send_verification_code_email(app, to_address, code):
    subject = "Verify your email for Expense Tracker"
    body = (
        f"Your verification code is: {code}\n\n"
        "Enter this code to confirm your email and finish creating your account. "
        "This code expires in 15 minutes.\n\n"
        "Don't see this email in your inbox? Check your spam or junk folder."
    )
    send_email(app, to_address, subject, body)