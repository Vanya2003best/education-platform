"""
Add is_admin_task flag to tasks table.
"""
from alembic import op
import sqlalchemy as sa

revision = "20240604_02"
down_revision = "20240604_01"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "is_admin_task",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        op.f("ix_tasks_is_admin_task"),
        "tasks",
        ["is_admin_task"],
        unique=False,
    )
    # Ensure existing rows default to false once column is in place
    op.execute(
        sa.text("UPDATE tasks SET is_admin_task = FALSE WHERE is_admin_task IS NULL")
    )

    # Drop the server default after backfilling to avoid future implicit defaults
    op.alter_column(
        "tasks",
        "is_admin_task",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_is_admin_task"), table_name="tasks")
    op.drop_column("tasks", "is_admin_task")