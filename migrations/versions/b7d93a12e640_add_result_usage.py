"""Preserve per-result usage without fabricating historical measurements."""

import sqlalchemy as sa
from alembic import op

revision = "b7d93a12e640"
down_revision = "e6b4c8d912af"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("example_results") as batch_op:
        batch_op.add_column(sa.Column("usage_json", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("example_results") as batch_op:
        batch_op.drop_column("usage_json")
