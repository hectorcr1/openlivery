"""Google Calendar OAuth and Calendar v3 function-tool execution."""

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Agent, GoogleCalendarConnection, GoogleCalendarOAuthState, User, now_utc
from ..security import decrypt_secret, encrypt_secret

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
GOOGLE_CALENDAR_CALLBACK_PATH = "/api/calendar/oauth/callback"


def _origin() -> str:
    settings = get_settings()
    public_url = (settings.google_calendar_public_url or settings.frontend_url).rstrip("/")
    # Accept either the public origin or the complete callback URI. The latter
    # is often copied directly from Google Cloud Console by an administrator.
    if public_url.endswith(GOOGLE_CALENDAR_CALLBACK_PATH):
        return public_url[: -len(GOOGLE_CALENDAR_CALLBACK_PATH)].rstrip("/")
    return public_url


def callback_url() -> str:
    return f"{_origin()}{GOOGLE_CALENDAR_CALLBACK_PATH}"


def configured() -> bool:
    settings = get_settings()
    return bool(settings.google_calendar_client_id and settings.google_calendar_client_secret)


def _state_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _consume_oauth_state(db: Session, state_hash: str) -> None:
    """Delete an OAuth state by its stable hash, including legacy text IDs."""
    db.execute(delete(GoogleCalendarOAuthState).where(GoogleCalendarOAuthState.state_hash == state_hash))


def _safe_next_path(value: str, agent_id: str) -> str:
    fallback = f"/agents/{agent_id}?tab=integrations"
    if not value.startswith(f"/agents/{agent_id}") or not value.startswith("/") or value.startswith("//"):
        return fallback
    return value


def begin_oauth(db: Session, user: User, agent: Agent, next_path: str = "") -> str:
    if not configured():
        raise HTTPException(503, "Google Calendar OAuth is not configured")
    state = secrets.token_urlsafe(32)
    settings = get_settings()
    db.add(GoogleCalendarOAuthState(
        state_hash=_state_hash(state), agency_id=user.agency_id, client_id=agent.client_id,
        agent_id=agent.id, user_id=user.id, next_path=_safe_next_path(next_path, str(agent.id)),
        expires_at=now_utc() + timedelta(minutes=max(1, min(settings.google_calendar_oauth_state_minutes, 30))),
    ))
    db.commit()
    params = {
        "client_id": settings.google_calendar_client_id,
        "redirect_uri": callback_url(),
        "response_type": "code",
        "scope": GOOGLE_CALENDAR_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        # A new consent screen ensures reconnecting can replace a revoked or
        # missing refresh token without relying on a prior browser session.
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def _callback_target(state: GoogleCalendarOAuthState, outcome: str) -> str:
    parsed = urlsplit(state.next_path)
    query = dict()
    if parsed.query:
        for part in parsed.query.split("&"):
            if "=" in part:
                key, value = part.split("=", 1)
                query[key] = value
    query["calendar"] = outcome
    return f"{_origin()}{urlunsplit(('', '', parsed.path, urlencode(query), ''))}"


async def finish_oauth(db: Session, state_value: str, code: str | None, error: str | None) -> str:
    state_hash = _state_hash(state_value)
    state = db.scalar(select(GoogleCalendarOAuthState).where(GoogleCalendarOAuthState.state_hash == state_hash))
    if not state or state.expires_at <= now_utc():
        if state:
            _consume_oauth_state(db, state_hash)
            db.commit()
        raise HTTPException(400, "The Google Calendar authorization has expired. Start again.")
    target = _callback_target(state, "error")
    success_target = _callback_target(state, "connected")
    _consume_oauth_state(db, state_hash)  # OAuth states are strictly single use, including failures.
    if error or not code:
        db.commit()
        return target

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code, "client_id": settings.google_calendar_client_id,
                "client_secret": settings.google_calendar_client_secret,
                "redirect_uri": callback_url(), "grant_type": "authorization_code",
            })
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        db.commit()
        return target
    if response.status_code >= 300 or not payload.get("access_token") or not payload.get("refresh_token"):
        db.commit()
        return target

    connection = db.scalar(select(GoogleCalendarConnection).where(
        GoogleCalendarConnection.client_id == state.client_id,
        GoogleCalendarConnection.agency_id == state.agency_id,
    ).with_for_update())
    if not connection:
        connection = GoogleCalendarConnection(
            agency_id=state.agency_id, client_id=state.client_id,
            encrypted_access_token=encrypt_secret(payload["access_token"]),
            encrypted_refresh_token=encrypt_secret(payload["refresh_token"]),
        )
        db.add(connection)
    else:
        connection.encrypted_access_token = encrypt_secret(payload["access_token"])
        connection.encrypted_refresh_token = encrypt_secret(payload["refresh_token"])
    expires_in = payload.get("expires_in")
    connection.token_expires_at = now_utc() + timedelta(seconds=int(expires_in)) if expires_in else None
    connection.granted_scopes = (payload.get("scope") or GOOGLE_CALENDAR_SCOPE).split()
    connection.status = "connected"
    connection.last_error = None
    connection.last_connected_at = now_utc()
    db.commit()
    return success_target


def connection_for_agent(db: Session, agent: Agent) -> GoogleCalendarConnection | None:
    return db.scalar(select(GoogleCalendarConnection).where(
        GoogleCalendarConnection.client_id == agent.client_id,
        GoogleCalendarConnection.agency_id == agent.agency_id,
    ))


def disconnect(db: Session, connection: GoogleCalendarConnection) -> None:
    db.delete(connection)
    db.commit()


async def _access_token(db: Session, connection: GoogleCalendarConnection) -> str:
    if connection.token_expires_at is None or connection.token_expires_at > now_utc() + timedelta(seconds=60):
        return decrypt_secret(connection.encrypted_access_token)
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": settings.google_calendar_client_id,
                "client_secret": settings.google_calendar_client_secret,
                "refresh_token": decrypt_secret(connection.encrypted_refresh_token),
                "grant_type": "refresh_token",
            })
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        connection.status = "error"
        connection.last_error = "Could not refresh the Google Calendar authorization"
        db.commit()
        raise RuntimeError("Could not refresh the Google Calendar authorization") from exc
    if response.status_code >= 300 or not payload.get("access_token"):
        connection.status = "error"
        connection.last_error = "Google Calendar authorization has expired or was revoked"
        db.commit()
        raise RuntimeError(connection.last_error)
    connection.encrypted_access_token = encrypt_secret(payload["access_token"])
    connection.token_expires_at = now_utc() + timedelta(seconds=int(payload.get("expires_in", 3600)))
    connection.status = "connected"
    connection.last_error = None
    db.commit()
    return payload["access_token"]


async def execute_google_calendar_tool(
    db: Session, connection: GoogleCalendarConnection, method: str, path: str, args: dict
) -> tuple[str, bool]:
    """Call a documented Calendar v3 endpoint and return compact JSON to the LLM."""
    try:
        token = await _access_token(db, connection)
        url = GOOGLE_CALENDAR_API + path.format(
            calendar_id=quote(str(args.get("calendar_id", "primary")), safe=""),
            event_id=quote(str(args.get("event_id", "")), safe=""),
            rule_id=quote(str(args.get("rule_id", "")), safe=""),
            setting=quote(str(args.get("setting", "")), safe=""),
        )
        params = args.get("params") if isinstance(args.get("params"), dict) else None
        body = args.get("body") if isinstance(args.get("body"), dict) else None
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, url, params=params, json=body, headers={"Authorization": f"Bearer {token}"})
        text = response.text
        if len(text) > 100_000:
            text = text[:100_000] + "... [truncated]"
        if response.status_code >= 300:
            try:
                details = response.json().get("error", {}).get("message", text)
            except (ValueError, AttributeError):
                details = text
            return f"Google Calendar API error ({response.status_code}): {details}", True
        result = text or '{"ok": true}'
        return f"Google Calendar API {response.status_code}: {result}", False
    except RuntimeError as exc:
        return f"Google Calendar authorization error: {exc}", True
    except httpx.HTTPError as exc:
        return f"Google Calendar request failed: {type(exc).__name__}", True
