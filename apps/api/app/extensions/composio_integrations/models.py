"""Persist only our authorization boundaries, never provider OAuth tokens."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base
from ...models import new_uuid, now_utc


class ComposioInstallation(Base):
    __tablename__ = "composio_installations"
    __table_args__ = (UniqueConstraint("agency_id", "toolkit_slug", name="uq_composio_installation"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    toolkit_slug: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(String(1000), default="")
    logo: Mapped[str] = mapped_column(String(500), default="")
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ComposioConnection(Base):
    __tablename__ = "composio_connections"
    __table_args__ = (UniqueConstraint("client_id", "toolkit_slug", name="uq_composio_connection"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    toolkit_slug: Mapped[str] = mapped_column(String(100))
    account_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ComposioOAuthAttempt(Base):
    __tablename__ = "composio_oauth_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    toolkit_slug: Mapped[str] = mapped_column(String(100))
    session_id: Mapped[str] = mapped_column(String(160), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ComposioAssignment(Base):
    __tablename__ = "composio_assignments"
    __table_args__ = (UniqueConstraint("agent_id", "toolkit_slug", name="uq_composio_assignment"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    agent_tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_tools.id", ondelete="CASCADE"), unique=True)
    toolkit_slug: Mapped[str] = mapped_column(String(100))
    session_id: Mapped[str] = mapped_column(String(160))
    tool_slugs: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
