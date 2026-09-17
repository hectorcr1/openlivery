"""Google Sheets OAuth and Sheets API v4 function-tool execution."""

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Agent, GoogleSheetsConnection, GoogleSheetsOAuthState, User, now_utc
from ..security import decrypt_secret, encrypt_secret

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SHEETS_API = "https://sheets.googleapis.com/v4"
GOOGLE_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
GOOGLE_OAUTH_CALLBACK_PATH = "/api/google/oauth/callback"


def _origin() -> str:
    settings = get_settings()
    public_url = (settings.google_public_url or settings.frontend_url).rstrip("/")
    for callback_path in (GOOGLE_OAUTH_CALLBACK_PATH, "/api/calendar/oauth/callback", "/api/sheets/oauth/callback"):
        if public_url.endswith(callback_path):
            return public_url[: -len(callback_path)].rstrip("/")
    return public_url


def callback_url() -> str:
    return f"{_origin()}{GOOGLE_OAUTH_CALLBACK_PATH}"


def configured() -> bool:
    settings = get_settings()
    # Calendar and Sheets use the same Google OAuth web application credentials.
    return bool(settings.google_client_id and settings.google_client_secret)


def _state_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _consume_oauth_state(db: Session, state_hash: str) -> None:
    db.execute(delete(GoogleSheetsOAuthState).where(GoogleSheetsOAuthState.state_hash == state_hash))


def _safe_next_path(value: str, agent_id: str) -> str:
    fallback = f"/agents/{agent_id}?tab=integrations"
    if not value.startswith(f"/agents/{agent_id}") or not value.startswith("/") or value.startswith("//"):
        return fallback
    return value


def begin_oauth(db: Session, user: User, agent: Agent, next_path: str = "") -> str:
    if not configured():
        raise HTTPException(503, "Google Sheets OAuth is not configured")
    state = secrets.token_urlsafe(32)
    settings = get_settings()
    db.add(GoogleSheetsOAuthState(
        state_hash=_state_hash(state), agency_id=user.agency_id, client_id=agent.client_id,
        agent_id=agent.id, user_id=user.id, next_path=_safe_next_path(next_path, str(agent.id)),
        expires_at=now_utc() + timedelta(minutes=max(1, min(settings.google_state_minutes, 30))),
    ))
    db.commit()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": callback_url(),
        "response_type": "code",
        "scope": GOOGLE_SHEETS_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def _callback_target(state: GoogleSheetsOAuthState, outcome: str) -> str:
    parsed = urlsplit(state.next_path)
    query: dict[str, str] = {}
    if parsed.query:
        for part in parsed.query.split("&"):
            if "=" in part:
                key, value = part.split("=", 1)
                query[key] = value
    query["sheets"] = outcome
    return f"{_origin()}{urlunsplit(('', '', parsed.path, urlencode(query), ''))}"


async def finish_oauth(db: Session, state_value: str, code: str | None, error: str | None) -> str:
    state_hash = _state_hash(state_value)
    state = db.scalar(select(GoogleSheetsOAuthState).where(GoogleSheetsOAuthState.state_hash == state_hash))
    if not state or state.expires_at <= now_utc():
        if state:
            _consume_oauth_state(db, state_hash)
            db.commit()
        raise HTTPException(400, "The Google Sheets authorization has expired. Start again.")
    target = _callback_target(state, "error")
    success_target = _callback_target(state, "connected")
    _consume_oauth_state(db, state_hash)
    if error or not code:
        db.commit()
        return target

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": callback_url(),
                "grant_type": "authorization_code",
            })
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        db.commit()
        return target
    if response.status_code >= 300 or not payload.get("access_token") or not payload.get("refresh_token"):
        db.commit()
        return target

    connection = db.scalar(select(GoogleSheetsConnection).where(
        GoogleSheetsConnection.client_id == state.client_id,
        GoogleSheetsConnection.agency_id == state.agency_id,
    ).with_for_update())
    if not connection:
        connection = GoogleSheetsConnection(
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
    connection.granted_scopes = (payload.get("scope") or GOOGLE_SHEETS_SCOPE).split()
    connection.status = "connected"
    connection.last_error = None
    connection.last_connected_at = now_utc()
    db.commit()
    return success_target


def connection_for_agent(db: Session, agent: Agent) -> GoogleSheetsConnection | None:
    return db.scalar(select(GoogleSheetsConnection).where(
        GoogleSheetsConnection.client_id == agent.client_id,
        GoogleSheetsConnection.agency_id == agent.agency_id,
    ))


def disconnect(db: Session, connection: GoogleSheetsConnection) -> None:
    db.delete(connection)
    db.commit()


async def _access_token(db: Session, connection: GoogleSheetsConnection) -> str:
    if connection.token_expires_at is None or connection.token_expires_at > now_utc() + timedelta(seconds=60):
        return decrypt_secret(connection.encrypted_access_token)
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": decrypt_secret(connection.encrypted_refresh_token),
                "grant_type": "refresh_token",
            })
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        connection.status = "error"
        connection.last_error = "Could not refresh the Google Sheets authorization"
        db.commit()
        raise RuntimeError(connection.last_error) from exc
    if response.status_code >= 300 or not payload.get("access_token"):
        connection.status = "error"
        connection.last_error = "Google Sheets authorization has expired or was revoked"
        db.commit()
        raise RuntimeError(connection.last_error)
    connection.encrypted_access_token = encrypt_secret(payload["access_token"])
    connection.token_expires_at = now_utc() + timedelta(seconds=int(payload.get("expires_in", 3600)))
    connection.status = "connected"
    connection.last_error = None
    db.commit()
    return payload["access_token"]


async def execute_google_sheets_tool(
    db: Session, connection: GoogleSheetsConnection, method: str, path: str, args: dict
) -> tuple[str, bool]:
    """Call a documented Sheets API v4 endpoint and return compact JSON."""
    try:
        token = await _access_token(db, connection)
        url = GOOGLE_SHEETS_API + path.format(
            spreadsheet_id=quote(str(args.get("spreadsheet_id", "")), safe=""),
            sheet_id=quote(str(args.get("sheet_id", "")), safe=""),
            range=quote(str(args.get("range", "")), safe="!:'"),
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
            return f"Google Sheets API error ({response.status_code}): {details}", True
        return f"Google Sheets API {response.status_code}: {text or '{\"ok\": true}'}", False
    except RuntimeError as exc:
        return f"Google Sheets authorization error: {exc}", True
    except httpx.HTTPError as exc:
        return f"Google Sheets request failed: {type(exc).__name__}", True
