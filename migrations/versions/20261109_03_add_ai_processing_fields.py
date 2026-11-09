"""Add note analysis fields and durable Celery dispatch metadata."""

from alembic import op
import sqlalchemy as sa

revision = "20261109_03"
down_revision = "20261109_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notes", sa.Column("concepts", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("notes", sa.Column("refinement_proposal", sa.Text(), nullable=True))
    op.add_column("note_processing_jobs", sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("note_processing_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("note_processing_jobs", sa.Column("worker_task_id", sa.String(255), nullable=True))
    op.add_column("note_processing_jobs", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("vector_cleanup_requests", sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("vector_cleanup_requests", "dispatched_at")
    op.drop_column("note_processing_jobs", "attempt_count")
    op.drop_column("note_processing_jobs", "worker_task_id")
    op.drop_column("note_processing_jobs", "started_at")
    op.drop_column("note_processing_jobs", "dispatched_at")
    op.drop_column("notes", "refinement_proposal")
    op.drop_column("notes", "concepts")
