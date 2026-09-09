import requests

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(app, to_address, subject, body):
    if app.config.get("MAIL_SUPPRESS_SEND"):
        print(f"[MAIL SUPPRESSED] To: {to_address}\nSubject: {subject}\n{body}")
        return

    payload = {
        "sender": {
            "name": app.config["BREVO_SENDER_NAME"],
            "email": app.config["BREVO_SENDER_EMAIL"],
        },
        "to": [{"email": to_address}],
        "subject": subject,
        "textContent": body,
    }
    headers = {
        "accept": "application/json",
        "api-key": app.config["BREVO_API_KEY"],
        "content-type": "application/json",
    }

    response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=10)
    if response.status_code >= 300:
        raise RuntimeError(f"Brevo API error {response.status_code}: {response.text}")


def send_reset_code_email(app, to_address, code):
    subject = "Your Prism password reset code"
    body = (
        f"Your password reset code is: {code}\n\n"
        "This code expires in 15 minutes. If you didn't request this, you can ignore this email.\n\n"
        "Don't see this email in your inbox? Check your spam or junk folder."
    )
    send_email(app, to_address, subject, body)


def send_verification_code_email(app, to_address, code):
    subject = "Verify your email for Prism"
    body = (
        f"Your verification code is: {code}\n\n"
        "Enter this code to confirm your email and finish creating your account. "
        "This code expires in 15 minutes.\n\n"
        "Don't see this email in your inbox? Check your spam or junk folder."
    )
    send_email(app, to_address, subject, body)