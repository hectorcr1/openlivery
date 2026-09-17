"""Agent-facing administration of the client-level Google Calendar grant."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import AgentGoogleCalendarTool, User
from ..schemas_google_calendar import GoogleCalendarIntegrationOut, GoogleCalendarOAuthStart, GoogleCalendarToolsUpdate
from ..services import google_calendar
from ..services.tools.google_calendar_specs import GOOGLE_CALENDAR_TOOLS, google_calendar_tool_names
from .agents import _agent


router = APIRouter(prefix="/agents/{agent_id}/integrations/google-calendar", tags=["Google Calendar"])


def _enabled_names(db: Session, agent_id: uuid.UUID) -> list[str]:
    return list(db.scalars(select(AgentGoogleCalendarTool.name).where(
        AgentGoogleCalendarTool.agent_id == agent_id, AgentGoogleCalendarTool.enabled.is_(True)
    )))


def _out(db: Session, agent_id: uuid.UUID, agent) -> GoogleCalendarIntegrationOut:
    connection = google_calendar.connection_for_agent(db, agent)
    return GoogleCalendarIntegrationOut(
        connected=bool(connection and connection.status == "connected"),
        status=connection.status if connection else "disconnected",
        oauth_ready=google_calendar.configured(),
        enabled_tools=_enabled_names(db, agent_id),
        last_error=connection.last_error if connection else None,
        last_connected_at=connection.last_connected_at if connection else None,
    )


@router.get("", response_model=GoogleCalendarIntegrationOut)
def integration(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(db, agent_id, _agent(db, user, agent_id))


@router.get("/tools")
def tools(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _agent(db, user, agent_id)
    enabled = set(_enabled_names(db, agent_id))
    return [{"name": item.name, "description": item.description, "read_only": item.read_only, "enabled": item.name in enabled} for item in GOOGLE_CALENDAR_TOOLS]


@router.put("/tools", response_model=GoogleCalendarIntegrationOut)
def update_tools(agent_id: uuid.UUID, payload: GoogleCalendarToolsUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    connection = google_calendar.connection_for_agent(db, agent)
    if not connection or connection.status != "connected":
        raise HTTPException(400, "Connect Google Calendar before enabling its tools")
    names = set(payload.enabled_tools)
    known = set(google_calendar_tool_names())
    if not names <= known:
        raise HTTPException(422, "One or more Google Calendar tools are unknown")
    existing = {row.name: row for row in db.scalars(select(AgentGoogleCalendarTool).where(AgentGoogleCalendarTool.agent_id == agent.id)).all()}
    for name in known:
        if name in existing:
            existing[name].enabled = name in names
        else:
            db.add(AgentGoogleCalendarTool(agent_id=agent.id, name=name, enabled=name in names))
    db.commit()
    return _out(db, agent_id, agent)


@router.post("/oauth/start")
def start_oauth(agent_id: uuid.UUID, payload: GoogleCalendarOAuthStart, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    return {"authorization_url": google_calendar.begin_oauth(db, user, agent, payload.next_path)}


@router.delete("", status_code=204)
def disconnect(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    connection = google_calendar.connection_for_agent(db, agent)
    if connection:
        google_calendar.disconnect(db, connection)
