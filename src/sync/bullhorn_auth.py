"""
Bullhorn OAuth authentication using username + password credentials.

Flow:
  1. GET /oauth/authorize with username/password  -> authorization code (via redirect)
  2. POST /oauth/token with auth code             -> access_token
  3. GET /rest-services/login with access_token   -> BhRestToken + restUrl

Required env vars:
  BULLHORN_CLIENT_ID
  BULLHORN_CLIENT_SECRET
  BULLHORN_API_USER
  BULLHORN_API_PASSWORD
  BULLHORN_AUTH_URL   (default: https://auth.bullhornstaffing.com)
  BULLHORN_LOGIN_URL  (default: https://rest.bullhornstaffing.com)
"""
from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

import httpx


def _env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise ValueError(f"Required env var {name!r} is not set")
    return value


@dataclass
class BullhornSession:
    rest_url: str           # base URL for all REST API calls
    rest_token: str         # BhRestToken query param required on every request
    refresh_token: str = ""
    expires_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    regional_auth_base: str = ""

    def expiring_soon(self, within_seconds: int = 120) -> bool:
        return datetime.datetime.now(datetime.timezone.utc) >= (
            self.expires_at - datetime.timedelta(seconds=within_seconds)
        )


async def get_session() -> BullhornSession:
    """Authenticate with Bullhorn and return a session with restUrl + BhRestToken."""
    client_id = _env("BULLHORN_CLIENT_ID")
    client_secret = _env("BULLHORN_CLIENT_SECRET")
    username = _env("BULLHORN_API_USER")
    password = _env("BULLHORN_API_PASSWORD")
    auth_base = os.getenv("BULLHORN_AUTH_URL", "https://auth.bullhornstaffing.com")
    login_base = os.getenv("BULLHORN_LOGIN_URL", "https://rest.bullhornstaffing.com")

    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        # Step 1a: get authorization code.
        # Bullhorn may 307-redirect to a regional auth server first, then that
        # server 302-redirects to the redirect_uri with ?code=.  We follow the
        # first redirect (regional) manually so we can still capture the second
        # redirect's Location header (which carries the code).
        auth_resp = await client.get(
            f"{auth_base}/oauth/authorize",
            params={
                "client_id": client_id,
                "response_type": "code",
                "action": "Login",
                "username": username,
                "password": password,
            },
        )

        # If we got a regional redirect (307/301/302) that doesn't yet carry a
        # code, follow it once and look for the code in the next Location.
        location = auth_resp.headers.get("location", "")
        match = re.search(r"[?&]code=([^&]+)", location)
        if not match and auth_resp.status_code in (301, 302, 307, 308) and location:
            # Step 1b: follow the regional redirect as-is — the Location URL
            # already contains all the original query params (client_id, username, etc.)
            regional_resp = await client.get(location)
            location = regional_resp.headers.get("location", "")
            match = re.search(r"[?&]code=([^&]+)", location)
            if not match:
                raise RuntimeError(
                    f"Bullhorn auth: no code after regional redirect. "
                    f"Status={regional_resp.status_code} Location={location!r}"
                )

        if not match:
            raise RuntimeError(
                f"Bullhorn auth: no code in redirect. Status={auth_resp.status_code} "
                f"Location={location!r}"
            )
        auth_code = unquote(match.group(1))

        # Step 2: exchange code for access_token.
        # Use the regional auth base if we were redirected there.
        regional_auth_base = auth_base
        if auth_resp.status_code in (301, 302, 307, 308):
            redirect_loc = auth_resp.headers.get("location", "")
            # Extract base from e.g. https://auth-west9.bullhornstaffing.com/oauth/authorize?...
            base_match = re.match(r"(https?://[^/]+)", redirect_loc)
            if base_match:
                regional_auth_base = base_match.group(1)

        token_resp = await client.post(
            f"{regional_auth_base}/oauth/token",
            params={
                "grant_type": "authorization_code",
                "code": auth_code,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        access_token = token_data.get("access_token", "")
        if not access_token:
            raise RuntimeError(f"Bullhorn auth: no access_token in response: {token_resp.text}")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 600))
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)

        # Step 3: REST login to get BhRestToken + restUrl (follow redirects)
        login_resp = await client.get(
            f"{login_base}/rest-services/login",
            params={"version": "*", "access_token": access_token},
            follow_redirects=True,
        )
        login_resp.raise_for_status()
        login_data = login_resp.json()
        rest_url = login_data.get("restUrl", "").rstrip("/")
        rest_token = login_data.get("BhRestToken", "")
        if not rest_url or not rest_token:
            raise RuntimeError(f"Bullhorn login: missing restUrl or BhRestToken: {login_data}")

    return BullhornSession(
        rest_url=rest_url,
        rest_token=rest_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        regional_auth_base=regional_auth_base,
    )


async def refresh_session(session: BullhornSession) -> BullhornSession:
    """Use refresh_token to get a new access_token and re-run REST login.
    Falls back to full re-auth if refresh token is missing or rejected.
    """
    if not session.refresh_token:
        return await get_session()

    client_id = _env("BULLHORN_CLIENT_ID")
    client_secret = _env("BULLHORN_CLIENT_SECRET")
    login_base = os.getenv("BULLHORN_LOGIN_URL", "https://rest.bullhornstaffing.com")
    auth_base = session.regional_auth_base or os.getenv("BULLHORN_AUTH_URL", "https://auth.bullhornstaffing.com")

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        token_resp = await client.post(
            f"{auth_base}/oauth/token",
            params={
                "grant_type": "refresh_token",
                "refresh_token": session.refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        if token_resp.status_code >= 400:
            # Refresh token expired — fall back to full re-auth
            return await get_session()

        token_data = token_resp.json()
        access_token = token_data.get("access_token", "")
        if not access_token:
            return await get_session()

        new_refresh_token = token_data.get("refresh_token", session.refresh_token)
        expires_in = int(token_data.get("expires_in", 600))
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)

        login_resp = await client.get(
            f"{login_base}/rest-services/login",
            params={"version": "*", "access_token": access_token},
        )
        login_resp.raise_for_status()
        login_data = login_resp.json()
        rest_url = login_data.get("restUrl", "").rstrip("/")
        rest_token = login_data.get("BhRestToken", "")
        if not rest_url or not rest_token:
            return await get_session()

    return BullhornSession(
        rest_url=rest_url,
        rest_token=rest_token,
        refresh_token=new_refresh_token,
        expires_at=expires_at,
        regional_auth_base=session.regional_auth_base,
    )


async def bullhorn_meta(session: BullhornSession, entity: str) -> dict:
    """Fetch field metadata for an entity. Useful for discovering undocumented Pay & Bill entities."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{session.rest_url}/meta/{entity}",
            params={"BhRestToken": session.rest_token, "fields": "*"},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Bullhorn meta {entity} failed {resp.status_code}: {resp.text[:500]}")
        return resp.json()


async def bullhorn_search(
    session: BullhornSession,
    entity: str,
    fields: str,
    query: str = "id:[1 TO *]",
    count: int = 500,
    start: int = 0,
) -> dict:
    """Search endpoint for indexed entities (e.g. Candidate, JobOrder)."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{session.rest_url}/search/{entity}",
            params={
                "BhRestToken": session.rest_token,
                "fields": fields,
                "query": query,
                "count": count,
                "start": start,
                "sort": "id",
            },
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Bullhorn search {entity} failed {resp.status_code}: {resp.text[:500]}")
        return resp.json()


async def bullhorn_query(
    session: BullhornSession,
    entity: str,
    fields: str,
    where: str = "id>0",
    count: int = 500,
    start: int = 0,
) -> dict:
    """Single paginated query against the Bullhorn REST API."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{session.rest_url}/query/{entity}",
            params={
                "BhRestToken": session.rest_token,
                "fields": fields,
                "where": where,
                "count": count,
                "start": start,
                "orderBy": "id",
            },
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Bullhorn query {entity} failed {resp.status_code}: {resp.text[:500]}"
            )
        return resp.json()
