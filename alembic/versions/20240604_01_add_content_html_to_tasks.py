"""add content_html to tasks

Revision ID: 20240604_01
Revises:
Create Date: 2024-06-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240604_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("content_html", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "content_html")