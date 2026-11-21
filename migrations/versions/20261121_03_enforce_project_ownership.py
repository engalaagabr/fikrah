"""Enforce matching project ownership for notes and conversations."""

from alembic import op

revision = "20261121_03"
down_revision = "20261121_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Counts only: never log note content, reassign ownership, or delete bad rows.
    # This guard is emitted in offline SQL as well as executed during upgrades.
    op.execute("""
        DO $$
        DECLARE
            invalid_notes bigint;
            invalid_conversations bigint;
        BEGIN
            SELECT count(*) INTO invalid_notes
            FROM notes AS child LEFT JOIN projects AS project
                ON project.id = child.project_id
            WHERE project.id IS NULL OR child.user_id IS DISTINCT FROM project.user_id;

            SELECT count(*) INTO invalid_conversations
            FROM chat_conversations AS child LEFT JOIN projects AS project
                ON project.id = child.project_id
            WHERE project.id IS NULL OR child.user_id IS DISTINCT FROM project.user_id;

            IF invalid_notes > 0 OR invalid_conversations > 0 THEN
                RAISE EXCEPTION
                    'Project ownership preflight failed: % notes and % conversations have inconsistent project ownership. Audit existing records before retrying.',
                    invalid_notes, invalid_conversations;
            END IF;
        END $$;
    """)
    op.create_unique_constraint("uq_projects_id_user_id", "projects", ["id", "user_id"])
    for table, constraint in (
        ("notes", "fk_notes_project_owner"),
        ("chat_conversations", "fk_chat_conversations_project_owner"),
    ):
        # Validate all existing rows before removing the old project-only FK.
        # PostgreSQL also rejects conflicting writes during constraint creation.
        op.create_foreign_key(
            constraint,
            table,
            "projects",
            ["project_id", "user_id"],
            ["id", "user_id"],
            ondelete="CASCADE",
        )
        op.drop_constraint(f"{table}_project_id_fkey", table, type_="foreignkey")


def downgrade() -> None:
    for table, constraint in (
        ("notes", "fk_notes_project_owner"),
        ("chat_conversations", "fk_chat_conversations_project_owner"),
    ):
        op.create_foreign_key(
            f"{table}_project_id_fkey",
            table,
            "projects",
            ["project_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.drop_constraint(constraint, table, type_="foreignkey")
    op.drop_constraint("uq_projects_id_user_id", "projects", type_="unique")
