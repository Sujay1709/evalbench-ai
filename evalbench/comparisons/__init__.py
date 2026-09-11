"""Read-only, paired comparisons of completed evaluation runs."""

from evalbench.comparisons.bootstrap import (
    BootstrapInterval,
    PairedBootstrapResult,
    paired_bootstrap,
)
from evalbench.comparisons.efficiency import (
    BenchmarkBoard,
    EfficiencySummary,
    LeaderboardEntry,
    build_leaderboards,
    summarize_efficiency,
)
from evalbench.comparisons.paired import (
    ComparisonError,
    ExampleComparison,
    RunComparison,
    compare_runs,
)
from evalbench.comparisons.segments import SegmentComparison, SegmentSummary, compare_segments

__all__ = [
    "BenchmarkBoard",
    "EfficiencySummary",
    "LeaderboardEntry",
    "build_leaderboards",
    "summarize_efficiency",
    "SegmentComparison",
    "SegmentSummary",
    "compare_segments",
    "BootstrapInterval",
    "PairedBootstrapResult",
    "paired_bootstrap",
    "ComparisonError",
    "ExampleComparison",
    "RunComparison",
    "compare_runs",
]
