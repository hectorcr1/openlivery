"""Agency integration catalog and client-scoped Composio accounts."""

from alembic import op
import sqlalchemy as sa

revision = "0055_composio_integrations"
down_revision = "0054_message_buttons"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "composio_installations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toolkit_slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("logo", sa.String(500), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agency_id", "toolkit_slug", name="uq_composio_installation"),
    )
    op.create_index("ix_composio_installations_agency_id", "composio_installations", ["agency_id"])
    op.create_table(
        "composio_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toolkit_slug", sa.String(100), nullable=False),
        sa.Column("account_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "toolkit_slug", name="uq_composio_connection"),
    )
    op.create_index("ix_composio_connections_agency_id", "composio_connections", ["agency_id"])
    op.create_index("ix_composio_connections_client_id", "composio_connections", ["client_id"])
    op.create_table(
        "composio_oauth_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toolkit_slug", sa.String(100), nullable=False),
        sa.Column("session_id", sa.String(160), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_composio_oauth_attempts_agency_id", "composio_oauth_attempts", ["agency_id"])
    op.create_table(
        "composio_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_tool_id", sa.Uuid(), sa.ForeignKey("agent_tools.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("toolkit_slug", sa.String(100), nullable=False),
        sa.Column("session_id", sa.String(160), nullable=False),
        sa.Column("tool_slugs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "toolkit_slug", name="uq_composio_assignment"),
    )
    op.create_index("ix_composio_assignments_agency_id", "composio_assignments", ["agency_id"])
    op.create_index("ix_composio_assignments_agent_id", "composio_assignments", ["agent_id"])


def downgrade():
    op.drop_table("composio_assignments")
    op.drop_table("composio_oauth_attempts")
    op.drop_table("composio_connections")
    op.drop_table("composio_installations")
