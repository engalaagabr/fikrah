"""Bind access tokens and refresh rotation to revocable session families."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261121_01"
down_revision = "20261109_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_sessions",
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Old JWTs have no session binding. Retire legacy refresh tokens rather than
    # keeping an alternate authentication path without immediate revocation.
    op.execute(
        "UPDATE refresh_sessions SET family_id = id, revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP)"
    )
    op.alter_column("refresh_sessions", "family_id", nullable=False)
    op.create_index("ix_refresh_sessions_family_id", "refresh_sessions", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_sessions_family_id", table_name="refresh_sessions")
    op.drop_column("refresh_sessions", "family_id")
