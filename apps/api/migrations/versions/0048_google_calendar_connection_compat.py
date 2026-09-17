"""Bring early Google Calendar connection tables up to the current schema."""

from alembic import op
import sqlalchemy as sa


revision = "0048_calendar_compat"
down_revision = "0047_google_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    connection_columns = {column["name"] for column in inspector.get_columns("google_calendar_connections")}
    if "last_connected_at" not in connection_columns:
        op.add_column("google_calendar_connections", sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("google_calendar_connections")}
    if "last_connected_at" in columns:
        op.drop_column("google_calendar_connections", "last_connected_at")
