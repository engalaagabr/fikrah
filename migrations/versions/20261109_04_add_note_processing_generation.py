"""Track AI processing attempts independently from note revisions."""

from alembic import op
import sqlalchemy as sa

revision = "20261109_04"
down_revision = "20261109_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notes",
        sa.Column("processing_generation", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "note_processing_jobs",
        sa.Column("processing_generation", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("note_processing_jobs", "processing_generation")
    op.drop_column("notes", "processing_generation")
