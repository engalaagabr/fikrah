"""Configurable SMTP delivery for account action links."""

import os
from email.message import EmailMessage
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiosmtplib


async def send_action_email(recipient: str, token: str, purpose: str) -> None:
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    base_url = os.getenv("EMAIL_ACTION_BASE_URL")
    if not host or not sender or not base_url:
        raise RuntimeError("SMTP_HOST, SMTP_FROM, and EMAIL_ACTION_BASE_URL must be configured")

    parts = urlsplit(base_url)
    if parts.scheme != "https" or not parts.netloc:
        raise RuntimeError("EMAIL_ACTION_BASE_URL must be an absolute HTTPS URL")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["token"] = token
    action_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    action = "Verify your email" if purpose == "verify_email" else "Reset your password"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"FIKRAH — {action}"
    message.set_content(f"{action}: {action_url}\n\nIf you did not request this, you can ignore this email.")

    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
    await aiosmtplib.send(
        message,
        hostname=host,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
        start_tls=not use_tls and os.getenv("SMTP_START_TLS", "true").lower() == "true",
        timeout=15,
    )
