from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from app.research.football.experimental_evaluator import (
    ExperimentalFootballEvaluation,
    TransparentPoissonPolicy,
    evaluate_transparent_poisson_baseline,
)
from app.research.football.match_analysis_input import (
    FootballAnalysisReadinessPolicy,
    FootballMatchAnalysisInput,
    build_match_analysis_inputs_from_benchmark,
)
from app.research.football.supplemental_history import (
    build_match_analysis_inputs_with_supplement,
)


@dataclass(frozen=True)
class FootballOperationalAnalysis:
    """Auditable pre-match analysis gate for MATRIX FÚTBOL.

    ``passed`` means that the requested analysis inputs were resolved and meet the
    minimum evidence requirements for *experimental evaluation*.  It never means
    that a model is promoted or that a real-money decision is allowed.
    """

    benchmark_id: str
    source_benchmark_status: str
    supplemental_evidence_used: bool
    source_equivalence_assumed: bool
    resolved_input_count: int
    rejected_or_unresolved_targets: tuple[str, ...]
    ready_for_experimental_evaluation_count: int
    money_decisions_enabled: bool
    passed: bool
    analysis_mode: str
    canonical_inputs: tuple[dict[str, Any], ...]
    readiness: tuple[dict[str, Any], ...]
    experimental_evaluations: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _source_equivalence_assumed(supplement: Mapping[str, Any] | None) -> bool:
    if supplement is None:
        return False
    methodology = supplement.get("methodology")
    if not isinstance(methodology, Mapping):
        return False
    # The safe policy is fail-closed: supplemental evidence is never silently
    # treated as equivalent to the primary provider.
    return bool(methodology.get("source_equivalence_assumed", False))


def build_football_operational_analysis(
    benchmark: Mapping[str, Any],
    *,
    supplement: Mapping[str, Any] | None = None,
    readiness_policy: FootballAnalysisReadinessPolicy = FootballAnalysisReadinessPolicy(),
    model_policy: TransparentPoissonPolicy = TransparentPoissonPolicy(),
) -> FootballOperationalAnalysis:
    """Build a deterministic, leakage-safe, non-monetary analysis artifact."""

    if not isinstance(benchmark, Mapping):
        raise TypeError("benchmark must be a mapping")
    benchmark_id = str(benchmark.get("benchmark_id") or "").strip()
    if not benchmark_id:
        raise ValueError("benchmark_id cannot be empty")

    if supplement is None:
        inputs, rejected = build_match_analysis_inputs_from_benchmark(benchmark)
    else:
        if not isinstance(supplement, Mapping):
            raise TypeError("supplement must be a mapping")
        inputs, rejected = build_match_analysis_inputs_with_supplement(benchmark, supplement)

    evaluations: tuple[ExperimentalFootballEvaluation, ...] = tuple(
        evaluate_transparent_poisson_baseline(
            value,
            readiness_policy=readiness_policy,
            model_policy=model_policy,
        )
        for value in inputs
    )
    ready_count = sum(1 for evaluation in evaluations if evaluation.readiness.ready)

    # This gate passes only when every resolved target is experimentally ready and
    # no target remains unresolved.  It intentionally does not promote any model.
    passed = bool(inputs) and not rejected and ready_count == len(inputs)

    return FootballOperationalAnalysis(
        benchmark_id=benchmark_id,
        source_benchmark_status=str(benchmark.get("benchmark_status") or "UNKNOWN"),
        supplemental_evidence_used=supplement is not None,
        source_equivalence_assumed=_source_equivalence_assumed(supplement),
        resolved_input_count=len(inputs),
        rejected_or_unresolved_targets=tuple(sorted(set(rejected))),
        ready_for_experimental_evaluation_count=ready_count,
        money_decisions_enabled=False,
        passed=passed,
        analysis_mode="EXPERIMENTAL_RESEARCH_ONLY",
        canonical_inputs=tuple(asdict(value) for value in inputs),
        readiness=tuple(asdict(evaluation.readiness) for evaluation in evaluations),
        experimental_evaluations=tuple(evaluation.as_dict() for evaluation in evaluations),
    )


def human_summary(result: FootballOperationalAnalysis) -> str:
    """Return a concise console report without presenting diagnostic output as bets."""

    status = "READY_FOR_EXPERIMENTAL_REVIEW" if result.passed else "BLOCKED"
    lines = [
        f"MATRIX_FOOTBALL_OPERATIONAL_STATUS={status}",
        f"benchmark_id={result.benchmark_id}",
        f"resolved_inputs={result.resolved_input_count}",
        f"experimental_ready={result.ready_for_experimental_evaluation_count}",
        f"unresolved={len(result.rejected_or_unresolved_targets)}",
        "money_decisions_enabled=False",
        "analysis_mode=EXPERIMENTAL_RESEARCH_ONLY",
    ]
    if result.rejected_or_unresolved_targets:
        lines.append("blocked_targets=" + ",".join(result.rejected_or_unresolved_targets))

    for evaluation in result.experimental_evaluations:
        readiness = evaluation["readiness"]
        probabilities = evaluation.get("probabilities")
        diagnostic = ""
        if isinstance(probabilities, dict):
            diagnostic = (
                " | DIAGNOSTIC_ONLY"
                f" H={probabilities['home_win']:.3f}"
                f" D={probabilities['draw']:.3f}"
                f" A={probabilities['away_win']:.3f}"
                f" O2.5={probabilities['over_2_5']:.3f}"
                f" BTTS={probabilities['btts']:.3f}"
            )
        lines.append(
            f"{evaluation['target_key']}"
            f" | readiness={readiness['status']}"
            f" | coverage={readiness['coverage_score']:.3f}"
            f" | model={evaluation['model_status']}"
            f" | decision={evaluation['decision']}"
            f"{diagnostic}"
        )
    return "\n".join(lines)
