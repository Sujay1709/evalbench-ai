"""Store append-only advisory judge evidence without changing run scores."""

import sqlalchemy as sa
from alembic import op

revision = "d4c7a2b9f610"
down_revision = "b7d93a12e640"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "judge_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("result_id", sa.Integer(), sa.ForeignKey("example_results.id"), nullable=False),
        sa.Column("rubric_id", sa.String(length=40), nullable=False),
        sa.Column("rubric_version", sa.String(length=12), nullable=False),
        sa.Column("rubric_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=12), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("judge_model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("response_id", sa.String(length=120), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("assessments_json", sa.JSON(), nullable=True),
        sa.Column("advisory_score", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_judge_attempts_result_id", "judge_attempts", ["result_id"])


def downgrade():
    op.drop_index("ix_judge_attempts_result_id", table_name="judge_attempts")
    op.drop_table("judge_attempts")
