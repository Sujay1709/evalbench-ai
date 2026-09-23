"""Record append-only secondary Kev decisions without touching primary scores."""

import sqlalchemy as sa
from alembic import op

revision = "a3e6d9c2f750"
down_revision = "f2e8c1d7a640"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kev_decision_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("result_id", sa.Integer(), sa.ForeignKey("example_results.id"), nullable=False),
        sa.Column("rubric_id", sa.String(length=40), nullable=False),
        sa.Column("rubric_version", sa.String(length=12), nullable=False),
        sa.Column("rubric_hash", sa.String(length=64), nullable=False),
        sa.Column("expected_run", sa.String(length=160), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("model_card_json", sa.JSON(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("ratings_json", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kev_decision_attempts_result_id", "kev_decision_attempts", ["result_id"])


def downgrade():
    op.drop_index("ix_kev_decision_attempts_result_id", table_name="kev_decision_attempts")
    op.drop_table("kev_decision_attempts")
