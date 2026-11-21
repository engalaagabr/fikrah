# Authentication and Accounts

## Status and Scope

This feature implements the first mobile-facing account API for the FastAPI backend. It covers email/password registration, email verification, Google sign-in, password recovery, access and refresh tokens, current-user lookup, and creation of each user's protected `General` project. It does not implement mobile UI, note/project CRUD, Google account disconnect, or account deletion.

## Confirmed Product Behavior

- Users can register and sign in with email/password or Google.
- Email/password users must verify their email before signing in.
- The mobile client sends a Google ID token. The backend verifies it and issues FIKRAH tokens.
- Automatic Google account creation/linking requires a verified Gmail address or verified Workspace identity with `hd`. A non-authoritative external email returns `401` for a new Google subject. An already linked subject can continue signing in, subject to the existing identity/email checks.
- Linking an unverified local account discards its unverified password and retires pending verification/reset links. Google sign-in must never activate a password chosen before mailbox ownership was established. Passwords on already verified local accounts are preserved.
- Every new account receives a protected `General` project.
- Access tokens are JWTs valid for 15 minutes. Refresh tokens are opaque, valid for 30 days, rotated on use, and revocable in PostgreSQL.
- Verification links expire after 24 hours. Password-reset links expire after one hour. Both are single-use; issuing a newer link invalidates earlier links for that purpose.
- Email sends have a 60-second per-address cooldown and a maximum of five messages per address per hour.
- SMTP and the HTTPS action-link base URL are configured by environment.

## API Contract

All routes use `/v1/auth`. JSON is used for requests and responses. Tokens are only returned from successful authentication or refresh calls. Validation errors use FastAPI's standard `422` response; authentication failures use `401`, and unverified email uses `403`. SMTP failures defer durable email delivery without changing a committed registration/recovery response or suppressing Google login tokens.

| Endpoint | Purpose and mobile call timing | Request | Response |
| --- | --- | --- | --- |
| `POST /register` | Create an email/password account and send verification. Call from the sign-up flow. | `{ "email": "person@example.com", "password": "..." }` | `202` with a generic message that avoids account enumeration. |
| `POST /verify-email` | Consume the one-time token from the verification link. Call when the user opens that link in the app. | `{ "token": "..." }` | `{ "message": "Email verified" }` |
| `POST /resend-verification` | Request another verification link. Call when the user asks to resend. | `{ "email": "person@example.com" }` | `202` with a generic message. |
| `POST /login` | Authenticate an email/password account. Call from sign-in. | `{ "email": "...", "password": "..." }` | Access token, refresh token, bearer type, and `expires_in: 900`. |
| `POST /google` | Verify the Google ID token supplied by the mobile Google sign-in flow. | `{ "id_token": "..." }` | The same token response as `/login`. |
| `POST /password-reset/request` | Send a one-time password-reset link. Call from the recovery flow. | `{ "email": "person@example.com" }` | `202` with a generic message. |
| `POST /password-reset/confirm` | Replace the password using the reset link. | `{ "token": "...", "new_password": "..." }` | `{ "message": "Password reset successfully" }`; all existing access and refresh sessions are revoked immediately. |
| `POST /refresh` | Rotate a refresh token and issue a fresh access/refresh pair. Call after an access-token expiry. | `{ "refresh_token": "..." }` | New token pair. The submitted refresh token is revoked. |
| `POST /logout` | Revoke the current access/refresh session family. Call when the user signs out. | `{ "refresh_token": "..." }` | `{ "message": "Signed out" }` |
| `GET /me` | Load the authenticated user's account summary. Call after sign-in or when restoring a session. | `Authorization: Bearer <access_token>` | `{ "id": "...", "email": "...", "email_verified": true }` |

### Mobile Integration Notes

- Store the refresh token in platform-secure storage. Send access tokens using the `Authorization: Bearer` header.
- On a `401` caused by an expired access token, call `/refresh` once and retry the original request with the new access token. If refresh fails, clear local credentials and ask the user to sign in again.
- Verification and reset email links include a `token` query parameter at the configured `EMAIL_ACTION_BASE_URL`; the mobile application should deep-link those links to the corresponding confirmation screen and submit the token to the API.
- Email/password registration and recovery return generic messages for unknown or already-registered addresses.

## Security and Technical Choices

- Password length is 15–128 characters with no composition rules. Passwords are stored using Argon2id via `pwdlib`.
- Google ID tokens are verified against `GOOGLE_CLIENT_ID`; the Google verifier validates the signature, issuer, audience, and time claims. The backend additionally requires a verified email and stable subject.
- Action tokens and refresh tokens are generated with a cryptographically secure random generator. Authentication lookups persist SHA-256 hashes. Pending action emails additionally hold an authenticated encrypted copy of their action token for delivery retries; it is scrubbed after successful sending or cancellation. Refresh tokens are never stored reversibly.
- JWT signing uses HS256 with `FIKRAH_JWT_SECRET`; the secret must contain at least 32 characters and must not be the public `.env.example` placeholder. API startup and token signing/verification reject unsafe values. Tokens include an issuer and a distinct access-token type.
- Email responses are intentionally generic for registration, resend, and recovery. Request throttling is persisted in PostgreSQL.
- PostgreSQL is the source of truth for account and session state. Cascading foreign keys remove authentication data when a user record is deleted.
- Authentication use cases use framework-independent command/result dataclasses and raise `AuthServiceError` values. The route layer maps API schemas to those commands and translates failures/results into HTTP responses.
- `AuthService` receives email delivery, Google token verification, and Google client ID configuration through `app/infrastructure/container.py`. The application layer does not import FastAPI, SMTP libraries, Google SDKs, or read provider configuration from the environment.
- Infrastructure adapters translate provider-specific delivery and token-verification failures into `EmailDeliveryError` and `GoogleIdentityTokenError`, which are defined at the authentication boundary.

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

Authentication tests cover password hashing, JWT claims and revocation, Google authority and linking, refresh replay, durable email retry, and tenant isolation. Opt-in PostgreSQL tests cover concurrent account creation, reset/refresh serialization, email claims, and the new migrations. These checks do not replace mobile integration or provider acceptance tests.

## References

- [FastAPI OAuth2 and JWT security](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [Google Auth ID-token verification](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

Account creation is serialized with transaction-scoped PostgreSQL identity advisory locks, including when no account row exists yet. Email/password registration and Google creation share the normalized email lock; Google also locks its stable subject. Concurrent first sign-ins create one user and one General project.

## Immediate session revocation

Access JWTs contain a `sid` identifying the refresh-token family. Every authenticated request validates that an unexpired, unrevoked refresh record still exists for that user/family. Rotation preserves the family. Logout revokes that family, including access JWTs and rotated descendants, while other device families remain active. Password reset revokes every family for the user.

Reusing a revoked refresh token commits revocation of its entire family before returning `401`; this includes the currently active replacement. Mobile must serialize refresh calls, store the replacement atomically, and sign in again after replay detection rather than retry a consumed refresh token.

Authentication mutations consistently lock the user before action/refresh records. Password verification and session issuance serialize with password reset, preventing a concurrent refresh from surviving reset.

Migration `20261121_01` adds family IDs and retires all legacy refresh tokens. Existing access JWTs without `sid` are rejected; users must sign in again after this security upgrade. No existing migration is edited. Token response bodies and public route paths are unchanged.

## Durable account emails

Migration `20261121_02` adds `email_deliveries`. Registration, verification resend, password recovery, and first Google registration save their email intents in the same transaction as the account/action changes. Immediate sending happens after commit, outside any database transaction. SMTP or template failures leave the intent pending; Celery Beat invokes `app.workers.tasks.deliver_account_emails` at the configured worker dispatch interval.

A sender claims a delivery for 60 seconds and fences acknowledgement with a unique claim token. Failures back off from 60 seconds up to one hour. Expired or retired action links are cancelled before sending. Sending is at least once: a crash after SMTP accepts a message but before acknowledgement can cause a duplicate. SMTP acceptance also does not guarantee arrival in the recipient's inbox.

Pending action tokens use Fernet authenticated encryption, with a separate HKDF domain derived from the private `FIKRAH_JWT_SECRET`; no new environment variable is needed. Rotating that secret invalidates old encrypted pending links, so affected users must request a fresh verification/reset email. Neither raw tokens nor ciphertext appear in delivery logs. Retention of completed delivery records remains an operations decision.
