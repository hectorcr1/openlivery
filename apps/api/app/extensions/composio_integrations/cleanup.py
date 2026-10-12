"""Remove temporary authorization sessions that were never completed."""

import logging
import uuid

import anyio
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import new_session
from ...models import now_utc
from . import service
from .models import ComposioOAuthAttempt


logger = logging.getLogger("openlivery.composio")


def revoke_agent_attempts(db: Session, agent_id: uuid.UUID) -> None:
    """Call from synchronous agent mutations before their transaction commits."""
    attempts = db.scalars(select(ComposioOAuthAttempt).where(
        ComposioOAuthAttempt.agent_id == agent_id,
    )).all()
    for attempt in attempts:
        if attempt.session_id:
            service.delete_session(attempt.session_id)
        db.delete(attempt)


async def revoke_client_attempts(db: Session, client_id: uuid.UUID) -> None:
    """Call before a client deletion cascades away temporary session IDs."""
    attempts = db.scalars(select(ComposioOAuthAttempt).where(
        ComposioOAuthAttempt.client_id == client_id,
    )).all()
    for attempt in attempts:
        if attempt.session_id:
            await anyio.to_thread.run_sync(service.delete_session, attempt.session_id)
        db.delete(attempt)


async def sweep_expired_attempts() -> None:
    with new_session() as db:
        attempts = db.scalars(select(ComposioOAuthAttempt).where(
            ComposioOAuthAttempt.expires_at < now_utc(),
        ).limit(100)).all()
        for attempt in attempts:
            try:
                if attempt.session_id:
                    await anyio.to_thread.run_sync(service.delete_session, attempt.session_id)
            except Exception as exc:
                logger.warning("Could not remove an expired authorization session: %s", type(exc).__name__)
                continue
            db.delete(attempt)
        db.commit()
