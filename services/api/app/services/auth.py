"""Clerk: verify session tokens, read a user's verified email, delete a user.

The app signs in with Clerk (email one-time codes) and sends `Authorization: Bearer <session token>`.
The token is a short-lived JWT; `clerk_backend_api` checks its signature against Clerk's keys. Users are
keyed by their Clerk user id in `users.auth_id` (dev accounts use `dev:<email>`).

Tests replace these functions; nothing here runs without `CLERK_SECRET_KEY`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import settings


class AuthUnavailable(Exception):
    """Clerk isn't configured on this server (no CLERK_SECRET_KEY)."""


class InvalidToken(Exception):
    """The bearer token is missing, expired, or not signed by our Clerk instance."""


@dataclass
class _Headers:
    headers: dict[str, str] = field(default_factory=dict)


def _secret() -> str:
    if not settings.clerk_secret_key:
        raise AuthUnavailable("CLERK_SECRET_KEY is not set")
    return settings.clerk_secret_key


def verify_session(token: str) -> str:
    """The Clerk user id (`sub`) of a valid session token."""
    from clerk_backend_api.security import authenticate_request
    from clerk_backend_api.security.types import AuthenticateRequestOptions

    state = authenticate_request(
        _Headers({"Authorization": f"Bearer {token}"}),  # the SDK reads this exact key
        AuthenticateRequestOptions(
            secret_key=_secret(),
            authorized_parties=settings.clerk_authorized_parties or None,
        ),
    )
    sub = (state.payload or {}).get("sub")
    if not state.is_signed_in or not isinstance(sub, str):
        raise InvalidToken(state.message or "invalid session token")
    return sub


def verified_email(clerk_user_id: str) -> str | None:
    """The user's primary email address, if Clerk has verified it."""
    from clerk_backend_api import Clerk

    with Clerk(bearer_auth=_secret()) as clerk:
        user = clerk.users.get(user_id=clerk_user_id)
    for e in user.email_addresses or []:
        status = getattr(e.verification, "status", None)
        verified = str(getattr(status, "value", status)) == "verified"
        if e.id == user.primary_email_address_id and verified:
            return e.email_address.strip().lower()
    return None


def delete_clerk_user(clerk_user_id: str) -> None:
    """Remove the Clerk account (store rules: deleting the account deletes the sign-in too)."""
    from clerk_backend_api import Clerk
    from clerk_backend_api.models import ClerkErrors

    with Clerk(bearer_auth=_secret()) as clerk:
        try:
            clerk.users.delete(user_id=clerk_user_id)
        except ClerkErrors as e:
            if getattr(e.raw_response, "status_code", None) != 404:  # already gone is fine
                raise
