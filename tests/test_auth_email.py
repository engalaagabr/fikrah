from email.message import EmailMessage

import pytest

from app.auth.email import send_action_email


@pytest.mark.parametrize(
    ("purpose", "subject", "html_phrase"),
    [
        ("verify_email", "Verify your email to sign in", "Verify email and continue"),
        ("reset_password", "Reset your FIKRAH password", "Reset password"),
    ],
)
@pytest.mark.asyncio
async def test_action_email_contains_plain_text_and_html(
    purpose: str,
    subject: str,
    html_phrase: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "FIKRAH <noreply@example.test>")
    monkeypatch.setenv("EMAIL_ACTION_BASE_URL", "https://app.example.test/action?source=email")
    monkeypatch.setenv("SMTP_START_TLS", "false")
    sent: list[EmailMessage] = []

    async def capture_send(message: EmailMessage, **_kwargs: object) -> None:
        sent.append(message)

    monkeypatch.setattr("app.auth.email.aiosmtplib.send", capture_send)

    await send_action_email("person@example.test", "safe-token", purpose)

    message = sent[0]
    assert message["Subject"] == f"FIKRAH — {subject}"
    assert message.get_content_type() == "multipart/alternative"
    plain_part, html_part = message.iter_parts()
    html_content = html_part.get_content()
    assert "source=email&amp;token=safe-token" in html_content
    assert html_phrase in html_content
    assert "source=email&token=safe-token" in plain_part.get_content()


@pytest.mark.asyncio
async def test_action_email_rejects_unknown_purpose(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="Unsupported email action purpose"):
        await send_action_email("person@example.test", "token", "login")
