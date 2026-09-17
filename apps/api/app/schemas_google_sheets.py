"""Public schemas for the client-level Google Sheets integration."""

from datetime import datetime

from pydantic import BaseModel, Field


class GoogleSheetsOAuthStart(BaseModel):
    next_path: str = Field(default="", max_length=500)


class GoogleSheetsToolsUpdate(BaseModel):
    enabled_tools: list[str] = Field(default_factory=list, max_length=64)


class GoogleSheetsIntegrationOut(BaseModel):
    provider: str = "google_sheets"
    connected: bool
    status: str
    oauth_ready: bool
    enabled_tools: list[str]
    last_error: str | None = None
    last_connected_at: datetime | None = None
