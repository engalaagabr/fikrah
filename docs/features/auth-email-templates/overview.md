# Authentication Email Templates

## Scope

The SMTP email sender renders account verification, password recovery, and new
account welcome emails from `static/emails/login.html`,
`static/emails/password_reset.html`, and `static/emails/welcome.html`. Each
message includes a plain-text part and an HTML alternative for email clients.

The login template is used for email verification because FIKRAH requires
verified email before password login. It does not add a passwordless-login flow.

## Rendering and delivery

Templates are loaded from the repository's `static/emails` directory and
rendered with HTML autoescaping. The service inserts the existing HTTPS action
URL and sends the message through the configured SMTP settings. Unsupported
email action purposes are rejected instead of falling through to another
template.

New email/password accounts receive a verification email and a welcome email
after creation. New Google accounts receive a welcome email after their account
and session are committed. Existing accounts do not receive another welcome
email when they sign in.

When using Docker Compose, the API sends these messages to the local Mailpit
service instead of an external SMTP server. Open `http://localhost:8025` to
inspect captured messages. The Compose configuration overrides SMTP host and
security settings inside the API container; a backend run directly on the host
uses the `localhost` SMTP settings in `.env`.
