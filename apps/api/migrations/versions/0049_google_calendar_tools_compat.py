"""Add Google Calendar agent permissions to legacy installations."""

from alembic import op
import sqlalchemy as sa


revision = "0049_calendar_tools_compat"
down_revision = "0048_calendar_compat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "agent_google_calendar_tools" not in tables:
        op.create_table(
            "agent_google_calendar_tools",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("agent_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("agent_id", "name", name="uq_agent_google_calendar_tool"),
        )
        op.create_index("ix_agent_google_calendar_tools_agent_id", "agent_google_calendar_tools", ["agent_id"])

    oauth_columns = {column["name"] for column in inspector.get_columns("google_calendar_oauth_states")}
    if "state_hash" not in oauth_columns:
        op.add_column("google_calendar_oauth_states", sa.Column("state_hash", sa.String(length=64), nullable=True))
        op.create_index("ix_google_calendar_oauth_states_state_hash", "google_calendar_oauth_states", ["state_hash"], unique=True)
    if "agent_id" not in oauth_columns:
        op.add_column("google_calendar_oauth_states", sa.Column("agent_id", sa.Uuid(), nullable=True))
    if "next_path" not in oauth_columns:
        op.add_column("google_calendar_oauth_states", sa.Column("next_path", sa.String(length=500), nullable=True))


def downgrade() -> None:
    # This migration only brings legacy schemas forward. Keep its data intact on downgrade.
    pass
