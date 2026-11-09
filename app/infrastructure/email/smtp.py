"""Configurable SMTP delivery for account emails."""

import os
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.auth.ports import EmailDeliveryError

EMAIL_TEMPLATE_DIRECTORY = Path(__file__).resolve().parents[3] / "static" / "emails"
EMAIL_TEMPLATES = Environment(
    loader=FileSystemLoader(EMAIL_TEMPLATE_DIRECTORY),
    autoescape=select_autoescape(("html", "xml")),
)
ACTION_EMAILS = {
    "verify_email": {
        "subject": "Verify your email to sign in",
        "template": "login.html",
        "text_action": "Verify your email to sign in",
    },
    "reset_password": {
        "subject": "Reset your FIKRAH password",
        "template": "password_reset.html",
        "text_action": "Reset your FIKRAH password",
    },
}


def _smtp_settings() -> dict[str, object]:
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    if not host or not sender:
        raise RuntimeError("SMTP_HOST and SMTP_FROM must be configured")

    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
    return {
        "hostname": host,
        "port": port,
        "sender": sender,
        "username": username,
        "password": password,
        "use_tls": use_tls,
        "start_tls": not use_tls
        and os.getenv("SMTP_START_TLS", "true").lower() == "true",
    }


async def _send(message: EmailMessage) -> None:
    settings = _smtp_settings()
    sender = str(settings.pop("sender"))
    message["From"] = sender
    await aiosmtplib.send(message, **settings, timeout=15)


async def send_action_email(recipient: str, token: str, purpose: str) -> None:
    try:
        email_action = ACTION_EMAILS[purpose]
    except KeyError as exc:
        raise ValueError(f"Unsupported email action purpose: {purpose}") from exc

    try:
        base_url = os.getenv("EMAIL_ACTION_BASE_URL")
        if not base_url:
            raise RuntimeError("EMAIL_ACTION_BASE_URL must be configured")

        parts = urlsplit(base_url)
        if parts.scheme != "https" or not parts.netloc:
            raise RuntimeError("EMAIL_ACTION_BASE_URL must be an absolute HTTPS URL")
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["token"] = token
        action_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )
        message = EmailMessage()
        message["To"] = recipient
        message["Subject"] = f"FIKRAH — {email_action['subject']}"
        message.set_content(
            f"{email_action['text_action']}: {action_url}\n\n"
            "If you did not request this, you can ignore this email."
        )
        template = EMAIL_TEMPLATES.get_template(email_action["template"])
        message.add_alternative(template.render(action_url=action_url), subtype="html")
        await _send(message)
    except (RuntimeError, OSError, ValueError, aiosmtplib.SMTPException) as error:
        raise EmailDeliveryError from error


async def send_welcome_email(recipient: str) -> None:
    try:
        message = EmailMessage()
        message["To"] = recipient
        message["Subject"] = "Welcome to FIKRAH"
        message.set_content(
            "Welcome to FIKRAH! Your personal knowledge space is ready.\n\n"
            "Capture your thoughts, connect your knowledge, and rediscover your ideas.\n\n"
            "Your thoughts, connected."
        )
        template = EMAIL_TEMPLATES.get_template("welcome.html")
        message.add_alternative(template.render(), subtype="html")
        await _send(message)
    except (RuntimeError, OSError, ValueError, aiosmtplib.SMTPException) as error:
        raise EmailDeliveryError from error
