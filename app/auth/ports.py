"""Application-facing contracts for authentication integrations."""


class EmailDeliveryError(Exception):
    """An email could not be rendered or delivered by the configured adapter."""


class GoogleIdentityTokenError(Exception):
    """An identity provider rejected a supplied Google ID token."""
