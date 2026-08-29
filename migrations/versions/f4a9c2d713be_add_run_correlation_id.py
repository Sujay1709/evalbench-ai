"""add run correlation id

Revision ID: f4a9c2d713be
Revises: c8e2d4f61a90
Create Date: 2026-08-29 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "f4a9c2d713be"
down_revision = "c8e2d4f61a90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "evaluation_runs",
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE evaluation_runs "
            "SET correlation_id = id "
            "WHERE correlation_id IS NULL"
        )
    )
    with op.batch_alter_table("evaluation_runs") as batch_op:
        batch_op.alter_column(
            "correlation_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_evaluation_runs_correlation_id",
            ["correlation_id"],
        )


def downgrade():
    with op.batch_alter_table("evaluation_runs") as batch_op:
        batch_op.drop_constraint(
            "uq_evaluation_runs_correlation_id",
            type_="unique",
        )
        batch_op.drop_column("correlation_id")
