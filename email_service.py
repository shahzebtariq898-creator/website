import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def smtp_configured() -> bool:
    return bool(
        os.environ.get("MAIL_USERNAME")
        and os.environ.get("MAIL_PASSWORD")
        and os.environ.get("MAIL_SERVER")
    )


def send_otp_email(to_email: str, otp: str, user_name: str = "") -> tuple[bool, str]:
    """Send 6-digit OTP to user's email. Returns (success, message)."""
    if not smtp_configured():
        return False, (
            "Email is not configured. Add MAIL_SERVER, MAIL_USERNAME, and "
            "MAIL_PASSWORD to a .env file (see .env.example)."
        )

    server = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    port = int(os.environ.get("MAIL_PORT", "587"))
    username = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    from_addr = os.environ.get("MAIL_FROM", username)
    use_tls = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"

    greeting = f"Hi {user_name}," if user_name else "Hi,"

    body = f"""{greeting}

Your password reset OTP for Gold Forecast is:

    {otp}

This code expires in 10 minutes. Do not share it with anyone.

If you did not request this, ignore this email.

— Gold Forecast
"""

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_email
    msg["Subject"] = f"Your OTP code: {otp} — Gold Forecast"
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(server, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.sendmail(from_addr, [to_email], msg.as_string())
        return True, "OTP sent to your email."
    except smtplib.SMTPAuthenticationError:
        return False, (
            "Email login failed. For Gmail use an App Password "
            "(Google Account → Security → App passwords)."
        )
    except Exception as e:
        return False, f"Could not send email: {e}"
