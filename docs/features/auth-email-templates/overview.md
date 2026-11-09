# Authentication Email Templates

## Scope

The SMTP action-email sender renders the account verification email from
`static/emails/login.html` and the password recovery email from
`static/emails/password_reset.html`. Both messages include a plain-text part and
an HTML alternative for email clients.

The login template is used for email verification because FIKRAH requires
verified email before password login. It does not add a passwordless-login flow.

## Rendering and delivery

Templates are loaded from the repository's `static/emails` directory and
rendered with HTML autoescaping. The service inserts the existing HTTPS action
URL and sends the message through the configured SMTP settings. Unsupported
email action purposes are rejected instead of falling through to another
template.
