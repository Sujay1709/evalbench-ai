"""add run error category

Revision ID: e6b4c8d912af
Revises: f4a9c2d713be
Create Date: 2026-09-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e6b4c8d912af"
down_revision = "f4a9c2d713be"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("evaluation_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("error_category", sa.String(length=48), nullable=True))

    op.execute(
        sa.text(
            "UPDATE evaluation_runs SET error_category = 'legacy_unclassified' "
            "WHERE status = 'failed' AND error_category IS NULL"
        )
    )


def downgrade():
    with op.batch_alter_table("evaluation_runs", schema=None) as batch_op:
        batch_op.drop_column("error_category")
