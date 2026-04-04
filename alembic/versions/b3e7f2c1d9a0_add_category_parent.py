"""add category parent

Revision ID: b3e7f2c1d9a0
Revises: 75ce3b1f4e5a
Create Date: 2026-03-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3e7f2c1d9a0"
down_revision: str | Sequence[str] | None = "75ce3b1f4e5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_categories_parent_id", "categories", ["parent_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_constraint("fk_categories_parent_id", type_="foreignkey")
        batch_op.drop_column("parent_id")
