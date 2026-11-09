# Authentication and Accounts

## Status and Scope

This feature implements the first mobile-facing account API for the FastAPI backend. It covers email/password registration, email verification, Google sign-in, password recovery, access and refresh tokens, current-user lookup, and creation of each user's protected `General` project. It does not implement mobile UI, note/project CRUD, Google account disconnect, or account deletion.

## Confirmed Product Behavior

- Users can register and sign in with email/password or Google.
- Email/password users must verify their email before signing in.
- The mobile client sends a Google ID token. The backend verifies it and issues FIKRAH tokens.
- A verified Google email is automatically linked to an existing account with the same normalized email.
- Every new account receives a protected `General` project.
- Access tokens are JWTs valid for 15 minutes. Refresh tokens are opaque, valid for 30 days, rotated on use, and revocable in PostgreSQL.
- Verification links expire after 24 hours. Password-reset links expire after one hour. Both are single-use; issuing a newer link invalidates earlier links for that purpose.
- Email sends have a 60-second per-address cooldown and a maximum of five messages per address per hour.
- SMTP and the HTTPS action-link base URL are configured by environment.

## API Contract

All routes use `/v1/auth`. JSON is used for requests and responses. Tokens are only returned from successful authentication or refresh calls. Validation errors use FastAPI's standard `422` response; authentication failures use `401`, unverified email uses `403`, and unavailable email delivery uses `503`.

| Endpoint | Purpose and mobile call timing | Request | Response |
| --- | --- | --- | --- |
| `POST /register` | Create an email/password account and send verification. Call from the sign-up flow. | `{ "email": "person@example.com", "password": "..." }` | `202` with a generic message that avoids account enumeration. |
| `POST /verify-email` | Consume the one-time token from the verification link. Call when the user opens that link in the app. | `{ "token": "..." }` | `{ "message": "Email verified" }` |
| `POST /resend-verification` | Request another verification link. Call when the user asks to resend. | `{ "email": "person@example.com" }` | `202` with a generic message. |
| `POST /login` | Authenticate an email/password account. Call from sign-in. | `{ "email": "...", "password": "..." }` | Access token, refresh token, bearer type, and `expires_in: 900`. |
| `POST /google` | Verify the Google ID token supplied by the mobile Google sign-in flow. | `{ "id_token": "..." }` | The same token response as `/login`. |
| `POST /password-reset/request` | Send a one-time password-reset link. Call from the recovery flow. | `{ "email": "person@example.com" }` | `202` with a generic message. |
| `POST /password-reset/confirm` | Replace the password using the reset link. | `{ "token": "...", "new_password": "..." }` | `{ "message": "Password reset successfully" }`; existing refresh sessions are revoked. |
| `POST /refresh` | Rotate a refresh token and issue a fresh access/refresh pair. Call after an access-token expiry. | `{ "refresh_token": "..." }` | New token pair. The submitted refresh token is revoked. |
| `POST /logout` | Revoke the current refresh token. Call when the user signs out. | `{ "refresh_token": "..." }` | `{ "message": "Signed out" }` |
| `GET /me` | Load the authenticated user's account summary. Call after sign-in or when restoring a session. | `Authorization: Bearer <access_token>` | `{ "id": "...", "email": "...", "email_verified": true }` |

### Mobile Integration Notes

- Store the refresh token in platform-secure storage. Send access tokens using the `Authorization: Bearer` header.
- On a `401` caused by an expired access token, call `/refresh` once and retry the original request with the new access token. If refresh fails, clear local credentials and ask the user to sign in again.
- Verification and reset email links include a `token` query parameter at the configured `EMAIL_ACTION_BASE_URL`; the mobile application should deep-link those links to the corresponding confirmation screen and submit the token to the API.
- Email/password registration and recovery return generic messages for unknown or already-registered addresses.

## Security and Technical Choices

- Password length is 15–128 characters with no composition rules. Passwords are stored using Argon2id via `pwdlib`.
- Google ID tokens are verified against `GOOGLE_CLIENT_ID`; the Google verifier validates the signature, issuer, audience, and time claims. The backend additionally requires a verified email and stable subject.
- Action tokens and refresh tokens are generated with a cryptographically secure random generator. Only SHA-256 hashes of these high-entropy tokens are persisted; plaintext tokens are sent once or returned once.
- JWT signing uses HS256 with `FIKRAH_JWT_SECRET`; the secret must contain at least 32 characters. Tokens include an issuer and a distinct access-token type.
- Email responses are intentionally generic for registration, resend, and recovery. Request throttling is persisted in PostgreSQL.
- PostgreSQL is the source of truth for account and session state. Cascading foreign keys remove authentication data when a user record is deleted.
- Authentication use cases use framework-independent command/result dataclasses and raise `AuthServiceError` values. The route layer maps API schemas to those commands and translates failures/results into HTTP responses.

## Environment Configuration

Required when using the corresponding flow:

| Variable | Use |
| --- | --- |
| `FIKRAH_JWT_SECRET` | HS256 signing key; at least 32 characters. |
| `GOOGLE_CLIENT_ID` | Expected audience for Google ID-token verification. |
| `EMAIL_ACTION_BASE_URL` | HTTPS mobile/web link that receives the `token` query parameter. |
| `SMTP_HOST`, `SMTP_FROM` | SMTP server and sender address. |

Optional SMTP settings: `SMTP_PORT` (default `587`), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS` (default `false`), and `SMTP_START_TLS` (default `true`). `DATABASE_URL` is required for database-backed routes and migrations.

## Persistence

The migration creates `users`, `projects`, `email_action_tokens`, `refresh_sessions`, and `email_send_attempts`. It deliberately adds only the account fields needed now. Future note, project-management, and account-lifecycle features must continue to scope records by `user_id` and honor the protected General project requirement.

## Verification

Authentication helper tests cover password hashing, JWT identity/type checks, and opaque-token hashing. API/database integration tests should be expanded as the application gains its PostgreSQL test service and mobile contract tests.

## References

- [FastAPI OAuth2 and JWT security](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [Google Auth ID-token verification](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
