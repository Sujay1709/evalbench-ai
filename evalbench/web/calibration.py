"""Read-only data preparation for the calibration workbench."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from evalbench.extensions import db
from evalbench.judges.pairwise import (
    PairwiseCalibrationError,
    PairwiseJudgment,
    PairwiseOrderSwapReport,
    summarize_order_swaps,
)
from evalbench.judges.repeatability import (
    RepeatabilityError,
    RepeatabilityReport,
    RepeatedJudgment,
    RepeatedScore,
    summarize_repeated_judgments,
)
from evalbench.models import (
    EvaluationRun,
    ExampleResult,
    HumanLabelSet,
    JudgeAttempt,
    PairwiseJudgeAttempt,
)


@dataclass(frozen=True)
class CalibrationEvidenceRow:
    """Evidence choices available for one result in a selected evaluation run."""

    result: ExampleResult
    judge_attempts: tuple[JudgeAttempt, ...]
    human_labels: tuple[HumanLabelSet, ...]
    selected_judge_id: str | None
    selected_human_id: str | None

    @property
    def is_partial(self) -> bool:
        return bool(self.selected_judge_id) != bool(self.selected_human_id)

    @property
    def is_complete_pair(self) -> bool:
        return bool(self.selected_judge_id and self.selected_human_id)


@dataclass(frozen=True)
class RepeatabilityEvidence:
    """One result/configuration group with repeated judge consistency evidence."""

    example_id: str
    report: RepeatabilityReport | None
    error: str | None


@dataclass(frozen=True)
class PairwiseEvidence:
    """Completed order-swap summary, or a precise incomplete-sample advisory."""

    report: PairwiseOrderSwapReport | None
    error: str | None


def eligible_calibration_runs() -> list[EvaluationRun]:
    """Return completed runs whose split can be represented honestly in a cohort."""
    return list(
        db.session.execute(
            db.select(EvaluationRun)
            .where(
                EvaluationRun.status == "completed",
                EvaluationRun.dataset_split.in_(("development", "holdout")),
            )
            .order_by(EvaluationRun.created_at.desc())
        ).scalars()
    )


def evidence_rows(
    run: EvaluationRun,
    selected_by_result: Mapping[int, tuple[str | None, str | None]],
) -> tuple[CalibrationEvidenceRow, ...]:
    """Load evidence choices in bounded queries without mutating persisted records."""
    results = tuple(run.results)
    result_ids = tuple(result.id for result in results)
    if not result_ids:
        return ()

    judges_by_result: defaultdict[int, list[JudgeAttempt]] = defaultdict(list)
    humans_by_result: defaultdict[int, list[HumanLabelSet]] = defaultdict(list)
    for attempt in db.session.execute(
        db.select(JudgeAttempt)
        .where(
            JudgeAttempt.result_id.in_(result_ids),
            JudgeAttempt.status == "completed",
        )
        .order_by(JudgeAttempt.created_at.desc())
    ).scalars():
        judges_by_result[attempt.result_id].append(attempt)
    for label in db.session.execute(
        db.select(HumanLabelSet)
        .where(HumanLabelSet.result_id.in_(result_ids))
        .order_by(HumanLabelSet.created_at.desc())
    ).scalars():
        humans_by_result[label.result_id].append(label)

    return tuple(
        CalibrationEvidenceRow(
            result=result,
            judge_attempts=tuple(judges_by_result[result.id]),
            human_labels=tuple(humans_by_result[result.id]),
            selected_judge_id=selected_by_result.get(result.id, (None, None))[0],
            selected_human_id=selected_by_result.get(result.id, (None, None))[1],
        )
        for result in results
    )


def selected_evidence(
    rows: Sequence[CalibrationEvidenceRow],
) -> tuple[tuple[tuple[str, str], ...], tuple[int, ...]]:
    """Return complete explicit pairs and result IDs with an incomplete selection."""
    pairs: list[tuple[str, str]] = []
    partial_result_ids: list[int] = []
    for row in rows:
        if row.is_partial:
            partial_result_ids.append(row.result.id)
        elif row.is_complete_pair:
            pairs.append((row.selected_judge_id, row.selected_human_id))
    return tuple(pairs), tuple(partial_result_ids)


def repeatability_evidence(
    rows: Sequence[CalibrationEvidenceRow],
) -> tuple[RepeatabilityEvidence, ...]:
    """Summarize repeated completed attempts without comparing unlike requests."""
    evidence: list[RepeatabilityEvidence] = []
    for row in rows:
        groups: defaultdict[tuple[str, ...], list[JudgeAttempt]] = defaultdict(list)
        for attempt in row.judge_attempts:
            identity = (
                attempt.judge_model,
                attempt.prompt_version,
                attempt.prompt_hash,
                attempt.rubric_id,
                attempt.rubric_version,
                attempt.rubric_hash,
            )
            groups[identity].append(attempt)

        for attempts in groups.values():
            if len(attempts) < 2:
                continue
            repeated = tuple(
                RepeatedJudgment(
                    attempt_id=attempt.id,
                    result_id=attempt.result_id,
                    status=attempt.status,
                    rubric_id=attempt.rubric_id,
                    rubric_version=attempt.rubric_version,
                    rubric_hash=attempt.rubric_hash,
                    judge_model=attempt.judge_model,
                    prompt_version=attempt.prompt_version,
                    prompt_hash=attempt.prompt_hash,
                    scores=tuple(
                        RepeatedScore(
                            criterion_id=item.get("criterion_id", ""),
                            score=item.get("score"),
                        )
                        for item in (attempt.assessments_json or [])
                        if isinstance(item, Mapping)
                    ),
                )
                for attempt in attempts
            )
            try:
                report = summarize_repeated_judgments(repeated)
            except RepeatabilityError as exc:
                evidence.append(RepeatabilityEvidence(row.result.example_id, None, str(exc)))
            else:
                evidence.append(RepeatabilityEvidence(row.result.example_id, report, None))
    return tuple(sorted(evidence, key=lambda item: (item.example_id, item.error or "")))


def pairwise_evidence(run: EvaluationRun) -> tuple[PairwiseEvidence, ...]:
    """Summarize pairwise attempts touching this run without writing records."""
    result_ids = tuple(result.id for result in run.results)
    if not result_ids:
        return ()

    attempts = db.session.execute(
        db.select(PairwiseJudgeAttempt)
        .where(
            db.or_(
                PairwiseJudgeAttempt.result_a_id.in_(result_ids),
                PairwiseJudgeAttempt.result_b_id.in_(result_ids),
            )
        )
        .order_by(PairwiseJudgeAttempt.created_at)
    ).scalars()
    groups: defaultdict[tuple[str, ...], list[PairwiseJudgment]] = defaultdict(list)
    for attempt in attempts:
        identity = (
            attempt.dataset_split,
            attempt.rubric_id,
            attempt.rubric_version,
            attempt.rubric_hash,
            attempt.judge_model,
            attempt.prompt_version,
            attempt.prompt_template_hash,
        )
        order = (
            (attempt.result_a_id, attempt.result_b_id)
            if attempt.presentation_order == "ab"
            else (attempt.result_b_id, attempt.result_a_id)
        )
        groups[identity].append(
            PairwiseJudgment(
                attempt_id=attempt.id,
                comparison_id=attempt.comparison_id,
                result_a_id=attempt.result_a_id,
                result_b_id=attempt.result_b_id,
                presentation_order=order,
                preferred_result_id=(attempt.choice_json or {}).get("preferred_result_id"),
                dataset_split=attempt.dataset_split,
                status=attempt.status,
                rubric_id=attempt.rubric_id,
                rubric_version=attempt.rubric_version,
                rubric_hash=attempt.rubric_hash,
                judge_model=attempt.judge_model,
                prompt_version=attempt.prompt_version,
                prompt_template_hash=attempt.prompt_template_hash,
            )
        )

    evidence: list[PairwiseEvidence] = []
    for judgments in groups.values():
        try:
            report = summarize_order_swaps(judgments)
        except PairwiseCalibrationError as exc:
            evidence.append(PairwiseEvidence(None, str(exc)))
        else:
            evidence.append(PairwiseEvidence(report, None))
    return tuple(evidence)
