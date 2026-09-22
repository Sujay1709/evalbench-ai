"""Store independent, append-only human rubric labels."""

import sqlalchemy as sa
from alembic import op

revision = "f2e8c1d7a640"
down_revision = "d4c7a2b9f610"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "human_label_sets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("result_id", sa.Integer(), sa.ForeignKey("example_results.id"), nullable=False),
        sa.Column("rubric_id", sa.String(length=40), nullable=False),
        sa.Column("rubric_version", sa.String(length=12), nullable=False),
        sa.Column("rubric_hash", sa.String(length=64), nullable=False),
        sa.Column("annotator_id", sa.String(length=64), nullable=False),
        sa.Column("presentation_hash", sa.String(length=64), nullable=False),
        sa.Column("ratings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_human_label_sets_result_id", "human_label_sets", ["result_id"])


def downgrade():
    op.drop_index("ix_human_label_sets_result_id", table_name="human_label_sets")
    op.drop_table("human_label_sets")
