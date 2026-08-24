"""add dataset split to evaluation runs

Revision ID: c8e2d4f61a90
Revises: aab0bf3b7b5b
Create Date: 2026-08-24 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c8e2d4f61a90"
down_revision = "aab0bf3b7b5b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "dataset_split",
            sa.String(length=24),
            nullable=False,
            server_default="legacy_mixed",
        ),
    )


def downgrade():
    op.drop_column("evaluation_runs", "dataset_split")
