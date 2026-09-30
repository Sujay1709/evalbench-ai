"""Store append-only order-swapped pairwise judge evidence."""

import sqlalchemy as sa
from alembic import op

revision = "b3e8d72c91a4"
down_revision = "a3e6d9c2f750"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pairwise_judge_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("comparison_id", sa.String(length=36), nullable=False),
        sa.Column(
            "result_a_id", sa.Integer(), sa.ForeignKey("example_results.id"), nullable=False
        ),
        sa.Column(
            "result_b_id", sa.Integer(), sa.ForeignKey("example_results.id"), nullable=False
        ),
        sa.Column(
            "preferred_result_id", sa.Integer(), sa.ForeignKey("example_results.id")
        ),
        sa.Column("dataset_split", sa.String(length=24), nullable=False),
        sa.Column("presentation_order", sa.String(length=2), nullable=False),
        sa.Column("rubric_id", sa.String(length=40), nullable=False),
        sa.Column("rubric_version", sa.String(length=12), nullable=False),
        sa.Column("rubric_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=12), nullable=False),
        sa.Column("prompt_template_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("judge_model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("response_id", sa.String(length=120), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("choice_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "result_a_id != result_b_id", name="ck_pairwise_distinct_results"
        ),
        sa.CheckConstraint(
            "dataset_split IN ('development', 'holdout')", name="ck_pairwise_split"
        ),
        sa.CheckConstraint("presentation_order IN ('ab', 'ba')", name="ck_pairwise_order"),
        sa.CheckConstraint(
            "preferred_result_id IS NULL OR preferred_result_id IN (result_a_id, result_b_id)",
            name="ck_pairwise_preferred_result",
        ),
        sa.UniqueConstraint(
            "comparison_id", "presentation_order", name="uq_pairwise_comparison_order"
        ),
    )
    op.create_index(
        "ix_pairwise_judge_attempts_comparison_id",
        "pairwise_judge_attempts",
        ["comparison_id"],
    )
    op.create_index(
        "ix_pairwise_judge_attempts_result_a_id", "pairwise_judge_attempts", ["result_a_id"]
    )
    op.create_index(
        "ix_pairwise_judge_attempts_result_b_id", "pairwise_judge_attempts", ["result_b_id"]
    )


def downgrade():
    op.drop_index("ix_pairwise_judge_attempts_result_b_id", table_name="pairwise_judge_attempts")
    op.drop_index("ix_pairwise_judge_attempts_result_a_id", table_name="pairwise_judge_attempts")
    op.drop_index("ix_pairwise_judge_attempts_comparison_id", table_name="pairwise_judge_attempts")
    op.drop_table("pairwise_judge_attempts")
