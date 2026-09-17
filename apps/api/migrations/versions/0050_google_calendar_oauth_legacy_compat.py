"""Allow the current OAuth flow to use legacy state tables."""

from alembic import op
import sqlalchemy as sa


revision = "0050_calendar_oauth_compat"
down_revision = "0049_calendar_tools_compat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"]: column for column in inspector.get_columns("google_calendar_oauth_states")}

    # Older Calendar releases stored these implementation-specific values as
    # mandatory fields. The current state record deliberately does not depend
    # on them, so make them optional while retaining all historic rows.
    for name in ("actor_type", "redirect_uri", "next_url"):
        if name in columns and not columns[name]["nullable"]:
            op.alter_column(
                "google_calendar_oauth_states",
                name,
                existing_type=columns[name]["type"],
                nullable=True,
            )


def downgrade() -> None:
    # Historic rows may not contain these values, so making them required again
    # would be unsafe.
    pass
