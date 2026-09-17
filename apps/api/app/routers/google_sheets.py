"""Agent-facing administration of the client-level Google Sheets grant."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import AgentGoogleSheetsTool, User
from ..schemas_google_sheets import GoogleSheetsIntegrationOut, GoogleSheetsOAuthStart, GoogleSheetsToolsUpdate
from ..services import google_sheets
from ..services.tools.google_sheets_specs import GOOGLE_SHEETS_TOOLS, google_sheets_tool_names
from .agents import _agent


router = APIRouter(prefix="/agents/{agent_id}/integrations/google-sheets", tags=["Google Sheets"])


def _enabled_names(db: Session, agent_id: uuid.UUID) -> list[str]:
    return list(db.scalars(select(AgentGoogleSheetsTool.name).where(
        AgentGoogleSheetsTool.agent_id == agent_id, AgentGoogleSheetsTool.enabled.is_(True)
    )))


def _out(db: Session, agent_id: uuid.UUID, agent) -> GoogleSheetsIntegrationOut:
    connection = google_sheets.connection_for_agent(db, agent)
    return GoogleSheetsIntegrationOut(
        connected=bool(connection and connection.status == "connected"),
        status=connection.status if connection else "disconnected",
        oauth_ready=google_sheets.configured(),
        enabled_tools=_enabled_names(db, agent_id),
        last_error=connection.last_error if connection else None,
        last_connected_at=connection.last_connected_at if connection else None,
    )


@router.get("", response_model=GoogleSheetsIntegrationOut)
def integration(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(db, agent_id, _agent(db, user, agent_id))


@router.get("/tools")
def tools(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _agent(db, user, agent_id)
    enabled = set(_enabled_names(db, agent_id))
    return [{"name": item.name, "description": item.description, "read_only": item.read_only, "enabled": item.name in enabled} for item in GOOGLE_SHEETS_TOOLS]


@router.put("/tools", response_model=GoogleSheetsIntegrationOut)
def update_tools(agent_id: uuid.UUID, payload: GoogleSheetsToolsUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    connection = google_sheets.connection_for_agent(db, agent)
    if not connection or connection.status != "connected":
        raise HTTPException(400, "Connect Google Sheets before enabling its tools")
    names = set(payload.enabled_tools)
    known = set(google_sheets_tool_names())
    if not names <= known:
        raise HTTPException(422, "One or more Google Sheets tools are unknown")
    existing = {row.name: row for row in db.scalars(select(AgentGoogleSheetsTool).where(AgentGoogleSheetsTool.agent_id == agent.id)).all()}
    for name in known:
        if name in existing:
            existing[name].enabled = name in names
        else:
            db.add(AgentGoogleSheetsTool(agent_id=agent.id, name=name, enabled=name in names))
    db.commit()
    return _out(db, agent_id, agent)


@router.post("/oauth/start")
def start_oauth(agent_id: uuid.UUID, payload: GoogleSheetsOAuthStart, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    return {"authorization_url": google_sheets.begin_oauth(db, user, agent, payload.next_path)}


@router.delete("", status_code=204)
def disconnect(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    connection = google_sheets.connection_for_agent(db, agent)
    if connection:
        google_sheets.disconnect(db, connection)
