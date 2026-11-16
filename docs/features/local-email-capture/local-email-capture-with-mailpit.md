# Local Email Capture with Mailpit

## Goal

Make account verification, password reset, and welcome email flows usable in
local development without sending messages to real recipients.

## Behavior

- Compose starts Mailpit alongside the backend stack.
- The API sends SMTP to `mailpit:1025` without TLS or credentials.
- Mailpit's web UI is available at `http://localhost:8025`.
- SMTP and UI host ports bind to loopback and can be changed with
  `FIKRAH_MAILPIT_SMTP_PORT` and `FIKRAH_MAILPIT_UI_PORT`.
- Messages are captured locally in memory and are not relayed to external SMTP.
- A backend run directly on the host uses the local SMTP values in `.env` and
  connects to `localhost` on the configured Mailpit SMTP port.

## Image and startup

Compose pins the Mailpit image to `axllent/mailpit:v1.33.0`. Its built-in
`readyz` health check gates API startup, so the email sink is available before
the application accepts requests.

## Scope

This service is only for local development. Production email delivery continues
to use the configurable SMTP settings supplied by the deployment environment.
