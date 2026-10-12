"""Agency catalog, client OAuth connections, and per-agent tool allowlists."""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...database import get_db
from ...deps import get_current_user
from ...models import Agent, AgentTool, User, now_utc
from ...routers.agents import _agent
from ...security import encrypt_secret
from ...services.tools.mcp_client import discover_mcp_tools
from . import service
from .models import ComposioAssignment, ComposioConnection, ComposioInstallation, ComposioOAuthAttempt


router = APIRouter(prefix="/composio", tags=["Composio integrations"])
logger = logging.getLogger("openlivery.composio")
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")


class InstallIn(BaseModel):
    slug: str = Field(min_length=1, max_length=100)


class AssignIn(BaseModel):
    tool_slugs: list[str] = Field(min_length=1, max_length=20)


def _require_config() -> None:
    if not service.configured():
        raise HTTPException(status_code=503, detail="Composio is not configured on this server")


def _slug(value: str) -> str:
    slug = value.strip().lower()
    if not SLUG_RE.fullmatch(slug):
        raise HTTPException(status_code=422, detail="Invalid toolkit slug")
    return slug


def _installation(db: Session, agency_id: uuid.UUID, slug: str) -> ComposioInstallation:
    row = db.scalar(select(ComposioInstallation).where(
        ComposioInstallation.agency_id == agency_id,
        ComposioInstallation.toolkit_slug == slug,
    ))
    if not row:
        raise HTTPException(status_code=404, detail="Toolkit is not installed for this agency")
    return row


def _connection(db: Session, user: User, client_id: uuid.UUID, slug: str) -> ComposioConnection:
    row = db.scalar(select(ComposioConnection).where(
        ComposioConnection.agency_id == user.agency_id,
        ComposioConnection.client_id == client_id,
        ComposioConnection.toolkit_slug == slug,
    ))
    if not row:
        raise HTTPException(status_code=409, detail="Connect this client's account first")
    return row


def _upstream_error(exc: Exception) -> HTTPException:
    # SDK exceptions can include request headers or links. Never surface them.
    logger.warning("Composio request failed: %s", type(exc).__name__)
    return HTTPException(status_code=502, detail="Composio is unavailable or rejected this request")


def _dispose_authorization_session(session_id: str) -> None:
    if not session_id:
        return
    try:
        service.delete_session(session_id)
    except Exception:
        logger.warning("Could not remove a Composio authorization session")


@router.get("/status")
def integration_status(user: User = Depends(get_current_user)):
    return {"configured": service.configured()}


@router.get("/catalog")
def catalog(
    cursor: str | None = None,
    limit: int = Query(default=40, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_config()
    try:
        page = service.list_toolkits(cursor, limit)
    except Exception as exc:
        raise _upstream_error(exc) from exc
    installed = set(db.scalars(select(ComposioInstallation.toolkit_slug).where(
        ComposioInstallation.agency_id == user.agency_id,
    )).all())
    for item in page["items"]:
        item["installed"] = item["slug"] in installed
    return page


@router.post("/install", status_code=status.HTTP_201_CREATED)
def install(payload: InstallIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_config()
    slug = _slug(payload.slug)
    existing = db.scalar(select(ComposioInstallation).where(
        ComposioInstallation.agency_id == user.agency_id,
        ComposioInstallation.toolkit_slug == slug,
    ))
    if existing:
        return {"slug": existing.toolkit_slug, "name": existing.name}
    try:
        details = service.get_toolkit(slug)
    except Exception as exc:
        raise _upstream_error(exc) from exc
    if not details["managed_auth"]:
        raise HTTPException(status_code=422, detail="This connector needs custom authorization and cannot be installed yet")
    row = ComposioInstallation(
        agency_id=user.agency_id,
        toolkit_slug=slug,
        name=details["name"][:180],
        description=details["description"][:1000],
        logo=details["logo"][:500],
        categories=details["categories"],
    )
    db.add(row)
    db.commit()
    return {"slug": row.toolkit_slug, "name": row.name}


@router.get("/agents/{agent_id}")
def agent_integrations(agent_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    installations = db.scalars(select(ComposioInstallation).where(
        ComposioInstallation.agency_id == user.agency_id,
    ).order_by(ComposioInstallation.name)).all()
    connections = {row.toolkit_slug: row for row in db.scalars(select(ComposioConnection).where(
        ComposioConnection.agency_id == user.agency_id,
        ComposioConnection.client_id == agent.client_id,
    )).all()}
    assignments = {row.toolkit_slug: row for row in db.scalars(select(ComposioAssignment).where(
        ComposioAssignment.agency_id == user.agency_id,
        ComposioAssignment.agent_id == agent.id,
    )).all()}
    return {
        "configured": service.configured(),
        "client_id": str(agent.client_id),
        "items": [
            {
                "slug": item.toolkit_slug,
                "name": item.name,
                "description": item.description,
                "logo": item.logo,
                "categories": item.categories,
                "connected": item.toolkit_slug in connections,
                "assigned": item.toolkit_slug in assignments,
                "tool_slugs": assignments[item.toolkit_slug].tool_slugs if item.toolkit_slug in assignments else [],
            }
            for item in installations
        ],
    }


@router.get("/toolkits/{slug}/tools")
def toolkit_tools(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_config()
    slug = _slug(slug)
    _installation(db, user.agency_id, slug)
    try:
        return service.list_tools(slug)
    except Exception as exc:
        raise _upstream_error(exc) from exc


@router.post("/agents/{agent_id}/connect/{slug}")
def connect(agent_id: uuid.UUID, slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_config()
    slug = _slug(slug)
    agent = _agent(db, user, agent_id)
    _installation(db, user.agency_id, slug)
    if db.scalar(select(ComposioConnection.id).where(
        ComposioConnection.client_id == agent.client_id,
        ComposioConnection.toolkit_slug == slug,
        ComposioConnection.agency_id == user.agency_id,
    )):
        raise HTTPException(status_code=409, detail="This client is already connected")
    attempt = ComposioOAuthAttempt(
        agency_id=user.agency_id,
        user_id=user.id,
        agent_id=agent.id,
        client_id=agent.client_id,
        toolkit_slug=slug,
        expires_at=now_utc() + timedelta(minutes=10),
    )
    db.add(attempt)
    db.commit()
    callback = f"{get_settings().frontend_url.rstrip('/')}/api/composio/oauth/callback?{urlencode({'state': str(attempt.id)})}"
    try:
        session_id, url = service.start_authorization(
            service.client_user_id(str(user.agency_id), str(agent.client_id)), slug, callback,
        )
    except Exception as exc:
        db.delete(attempt)
        db.commit()
        raise _upstream_error(exc) from exc
    if not url.startswith("https://connect.composio.dev/"):
        _dispose_authorization_session(session_id)
        db.delete(attempt)
        db.commit()
        raise HTTPException(status_code=502, detail="Composio returned an invalid authorization link")
    attempt.session_id = session_id
    try:
        db.commit()
    except Exception:
        db.rollback()
        _dispose_authorization_session(session_id)
        raise
    return {"authorization_url": url}


@router.get("/oauth/callback")
def oauth_callback(
    state: uuid.UUID,
    status: str = "failed",
    connected_account_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    attempt = db.scalar(select(ComposioOAuthAttempt).where(
        ComposioOAuthAttempt.id == state,
        ComposioOAuthAttempt.user_id == user.id,
        ComposioOAuthAttempt.agency_id == user.agency_id,
    ))
    if not attempt:
        raise HTTPException(status_code=400, detail="The authorization attempt is invalid or expired")
    agent = _agent(db, user, attempt.agent_id)
    if agent.client_id != attempt.client_id:
        raise HTTPException(status_code=400, detail="The agent's client changed during authorization")
    return_url = f"{get_settings().frontend_url.rstrip('/')}/agents/{attempt.agent_id}/tools"
    expired = attempt.expires_at < datetime.now(timezone.utc)
    db.delete(attempt)  # One-time state, even when the provider reports failure.
    if expired or status != "success" or not connected_account_id:
        db.commit()
        _dispose_authorization_session(attempt.session_id)
        return RedirectResponse(f"{return_url}?composio=failed", status_code=303)
    user_id = service.client_user_id(str(user.agency_id), str(attempt.client_id))
    try:
        valid = service.active_account(user_id, attempt.toolkit_slug, connected_account_id)
    except Exception as exc:
        raise _upstream_error(exc) from exc
    if not valid:
        db.commit()
        _dispose_authorization_session(attempt.session_id)
        raise HTTPException(status_code=400, detail="The authorized account does not belong to this client")
    existing = db.scalar(select(ComposioConnection).where(
        ComposioConnection.agency_id == user.agency_id,
        ComposioConnection.client_id == attempt.client_id,
        ComposioConnection.toolkit_slug == attempt.toolkit_slug,
    ))
    if existing:
        db.commit()
        _dispose_authorization_session(attempt.session_id)
        raise HTTPException(status_code=409, detail="This client is already connected")
    db.add(ComposioConnection(
        agency_id=user.agency_id,
        client_id=attempt.client_id,
        toolkit_slug=attempt.toolkit_slug,
        account_id=connected_account_id,
    ))
    db.commit()
    _dispose_authorization_session(attempt.session_id)
    return RedirectResponse(f"{return_url}?composio=connected", status_code=303)


def _tool_alias(db: Session, agent_id: uuid.UUID) -> str:
    occupied = set(db.scalars(select(AgentTool.name).where(AgentTool.agent_id == agent_id)).all())
    for number in range(1, 100):
        name = f"c{number}"
        if name not in occupied:
            return name
    raise HTTPException(status_code=409, detail="This agent has too many connected toolkits")


@router.put("/agents/{agent_id}/assign/{slug}")
async def assign(
    agent_id: uuid.UUID,
    slug: str,
    payload: AssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_config()
    slug = _slug(slug)
    agent = _agent(db, user, agent_id)
    _installation(db, user.agency_id, slug)
    connection = _connection(db, user, agent.client_id, slug)
    selected = list(dict.fromkeys(payload.tool_slugs))
    if len(selected) != len(payload.tool_slugs):
        raise HTTPException(status_code=422, detail="Choose each tool only once")
    user_id = service.client_user_id(str(user.agency_id), str(agent.client_id))
    try:
        active = await anyio.to_thread.run_sync(service.active_account, user_id, slug, connection.account_id)
        available = await anyio.to_thread.run_sync(service.list_tools, slug)
    except Exception as exc:
        raise _upstream_error(exc) from exc
    if not active:
        raise HTTPException(status_code=409, detail="This client's account is no longer active")
    supported = {tool["slug"] for tool in available if tool["supported"]}
    if not set(selected).issubset(supported):
        raise HTTPException(status_code=422, detail="Select only supported tools from this toolkit")
    existing = db.scalar(select(ComposioAssignment).where(
        ComposioAssignment.agency_id == user.agency_id,
        ComposioAssignment.agent_id == agent.id,
        ComposioAssignment.toolkit_slug == slug,
    ))
    if existing:
        tool = db.get(AgentTool, existing.agent_tool_id)
        if not tool:
            raise HTTPException(status_code=409, detail="The managed tool was deleted; remove the assignment first")
    else:
        tool = None
        alias = _tool_alias(db, agent.id)
    try:
        session_id, url, headers = await anyio.to_thread.run_sync(
            service.create_mcp_session, user_id, slug, connection.account_id, selected,
        )
    except Exception as exc:
        raise _upstream_error(exc) from exc
    try:
        cached = await discover_mcp_tools(url, "streamable_http", headers)
        if not set(selected).issubset({tool["name"] for tool in cached}):
            raise ValueError("The session did not expose all selected tools")
    except Exception as exc:
        try:
            await anyio.to_thread.run_sync(service.delete_session, session_id)
        except Exception:
            logger.warning("Failed to clean up a Composio session after discovery failure")
        raise _upstream_error(exc) from exc
    old_session_id = existing.session_id if existing else None
    try:
        if not existing:
            tool = AgentTool(agent_id=agent.id, type="mcp", name=alias)
            db.add(tool)
            db.flush()
            existing = ComposioAssignment(
                agency_id=user.agency_id,
                agent_id=agent.id,
                agent_tool_id=tool.id,
                toolkit_slug=slug,
                session_id=session_id,
                tool_slugs=selected,
            )
            db.add(existing)
        tool.description = f"Composio: {slug}"
        tool.url = url
        tool.transport = "streamable_http"
        tool.encrypted_headers = encrypt_secret(json.dumps(headers))
        tool.cached_tools = cached
        tool.tools_cached_at = now_utc()
        tool.enabled_tools = selected
        tool.enabled = True
        existing.session_id = session_id
        existing.tool_slugs = selected
        db.commit()
    except Exception:
        db.rollback()
        try:
            await anyio.to_thread.run_sync(service.delete_session, session_id)
        except Exception:
            logger.warning("Failed to clean up a Composio session after a database failure")
        raise
    if old_session_id:
        try:
            await anyio.to_thread.run_sync(service.delete_session, old_session_id)
        except Exception:
            logger.warning("Could not remove superseded Composio session")
    return {"assigned": True, "tool_slugs": selected}


@router.delete("/agents/{agent_id}/assign/{slug}", status_code=204)
async def unassign(agent_id: uuid.UUID, slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    slug = _slug(slug)
    assignment = db.scalar(select(ComposioAssignment).where(
        ComposioAssignment.agency_id == user.agency_id,
        ComposioAssignment.agent_id == agent.id,
        ComposioAssignment.toolkit_slug == slug,
    ))
    if not assignment:
        raise HTTPException(status_code=404, detail="Agent integration not found")
    try:
        await anyio.to_thread.run_sync(service.delete_session, assignment.session_id)
    except Exception as exc:
        raise _upstream_error(exc) from exc
    tool = db.get(AgentTool, assignment.agent_tool_id)
    db.delete(assignment)
    if tool:
        db.delete(tool)
    db.commit()


@router.delete("/agents/{agent_id}/connect/{slug}", status_code=204)
async def disconnect(agent_id: uuid.UUID, slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = _agent(db, user, agent_id)
    slug = _slug(slug)
    connection = _connection(db, user, agent.client_id, slug)
    assignments = db.scalars(select(ComposioAssignment).join(Agent, Agent.id == ComposioAssignment.agent_id).where(
        ComposioAssignment.agency_id == user.agency_id,
        Agent.client_id == agent.client_id,
        ComposioAssignment.toolkit_slug == slug,
    )).all()
    try:
        for assignment in assignments:
            await anyio.to_thread.run_sync(service.delete_session, assignment.session_id)
        await anyio.to_thread.run_sync(service.delete_account, connection.account_id)
    except Exception as exc:
        raise _upstream_error(exc) from exc
    for assignment in assignments:
        tool = db.get(AgentTool, assignment.agent_tool_id)
        db.delete(assignment)
        if tool:
            db.delete(tool)
    db.delete(connection)
    db.commit()
