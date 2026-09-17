"""Shared callback endpoint for every Google OAuth integration."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GoogleCalendarOAuthState, GoogleSheetsOAuthState
from ..services import google_calendar, google_sheets


router = APIRouter(prefix="/google/oauth", tags=["Google OAuth"])


@router.get("/callback")
async def oauth_callback(
    state: str = Query(max_length=256), code: str | None = Query(default=None, max_length=8192),
    error: str | None = Query(default=None, max_length=256), db: Session = Depends(get_db),
):
    """Finish the provider flow identified by the one-use, hashed state."""
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    is_calendar = db.scalar(select(GoogleCalendarOAuthState.state_hash).where(
        GoogleCalendarOAuthState.state_hash == state_hash
    ))
    if is_calendar:
        target = await google_calendar.finish_oauth(db, state, code, error)
    else:
        is_sheets = db.scalar(select(GoogleSheetsOAuthState.state_hash).where(
            GoogleSheetsOAuthState.state_hash == state_hash
        ))
        if not is_sheets:
            raise HTTPException(400, "The Google authorization has expired. Start again.")
        target = await google_sheets.finish_oauth(db, state, code, error)
    return RedirectResponse(target, status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
