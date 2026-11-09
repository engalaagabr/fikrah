# Phase: Account Access

## Goal

Provide secure personal accounts for the mobile application and enforce a clear user identity boundary before adding user-owned knowledge features.

## Scope

- Email/password registration and login with mandatory email verification.
- Google ID-token sign-in and linking for verified matching email addresses.
- Email verification and password reset through configurable SMTP links.
- HTML email templates for verification before login and password reset, with plain-text alternatives.
- Short-lived JWT access tokens and rotating, revocable opaque refresh tokens.
- Current-user endpoint and protected `General` project creation.
- PostgreSQL persistence, schema migration, and API contract documentation.

## Completion Criteria

- All account flows are exposed through documented versioned API endpoints.
- Credentials, email action tokens, and refresh tokens follow the documented storage protections.
- Account/session schema migration and focused tests are present.
- Mobile integration can use the documented request and response contracts.

## Out of Scope

- Mobile UI and platform credential storage implementation.
- Note, project CRUD, AI workflows, and social login providers other than Google.
- Deployment-specific SMTP, Google OAuth client, or production signing-secret provisioning.
