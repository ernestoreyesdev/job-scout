from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException

from app.config import Settings, get_settings


@dataclass(frozen=True)
class CurrentUser:
    """A verified user; admin comes from role "admin" in their app_metadata, which only the service role can set."""

    id: str
    access_token: str
    admin: bool = False


def current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Verifies the forwarded Supabase access token with Supabase Auth."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token.")
    token = authorization.removeprefix("Bearer ")

    res = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
        headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if res.status_code != 200:
        raise HTTPException(401, "Invalid or expired session.")

    body = res.json()
    return CurrentUser(id=body["id"], access_token=token, admin=(body.get("app_metadata") or {}).get("role") == "admin")


def admin_user(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    """The current user when they're an admin; anyone else gets a 403."""
    if not user.admin:
        raise HTTPException(403, "Only admins can do this.")
    return user
