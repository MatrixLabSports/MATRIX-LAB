from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .live_slo import LiveTiming


LIVE_STATES = frozenset({"DISCARD", "WATCH", "PRE_SIGNAL", "ENTRY", "WINDOW_CLOSED"})
LIVE_MODES = frozenset({"REPLAY", "SHADOW"})


@dataclass(frozen=True)
class LiveValidationSample:
    sport: str
    market: str
    mode: str
    timing: LiveTiming
    predicted_state: str
    oracle_entry_eligible: bool

    def __post_init__(self) -> None:
        if self.sport not in {"football", "tennis"}:
            raise ValueError("LIVE_SPORT_INVALID")
        if not self.market.strip():
            raise ValueError("LIVE_MARKET_REQUIRED")
        if self.mode not in LIVE_MODES:
            raise ValueError("LIVE_MODE_INVALID")
        if self.predicted_state not in LIVE_STATES:
            raise ValueError("LIVE_STATE_INVALID")
        # Force timing validation now rather than lazily in a later report.
        _ = self.timing.end_to_end_ms


@dataclass(frozen=True)
class LiveSLOPolicy:
    minimum_samples: int
    maximum_p95_ms: float
    maximum_p99_ms: float
    maximum_missed_window_rate: float
    maximum_stale_signal_rate: float
    maximum_decision_too_late_rate: float
    maximum_false_positive_rate: float
    maximum_false_negative_rate: float
    stale_threshold_ms: float
    require_shadow: bool = True

    def __post_init__(self) -> None:
        if self.minimum_samples < 1:
            raise ValueError("LIVE_MINIMUM_SAMPLES_INVALID")
        if self.maximum_p95_ms < 0 or self.maximum_p99_ms < self.maximum_p95_ms or self.stale_threshold_ms < 0:
            raise ValueError("LIVE_LATENCY_POLICY_INVALID")
        for value in (
            self.maximum_missed_window_rate,
            self.maximum_stale_signal_rate,
            self.maximum_decision_too_late_rate,
            self.maximum_false_positive_rate,
            self.maximum_false_negative_rate,
        ):
            if not 0 <= value <= 1:
                raise ValueError("LIVE_RATE_POLICY_INVALID")


def _pct(values: Sequence[float], q: float) -> float:
    vals = sorted(float(x) for x in values)
    if not vals:
        raise ValueError("EMPTY_LIVE_SAMPLE")
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = int(pos); hi = min(lo + 1, len(vals) - 1); frac = pos - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def _stage_values(sample: LiveValidationSample) -> tuple[float, ...]:
    t = sample.timing
    return (
        t.event_to_provider_ms,
        t.provider_to_ingest_ms,
        t.ingest_to_normalize_ms,
        t.normalize_to_feature_ms,
        t.feature_to_inference_ms,
        t.inference_to_market_ms,
        t.market_to_signal_ms,
        t.signal_to_visible_ms,
    )


def live_validation_report(samples: Sequence[LiveValidationSample], *, stale_threshold_ms: float) -> dict[str, object]:
    if not samples:
        raise ValueError("EMPTY_LIVE_SAMPLE")
    if stale_threshold_ms < 0:
        raise ValueError("STALE_THRESHOLD_INVALID")
    sport_market = {(s.sport, s.market) for s in samples}
    if len(sport_market) != 1:
        raise ValueError("LIVE_REPORT_MIXED_SPORT_MARKET")

    e2e = [s.timing.end_to_end_ms for s in samples]
    stage_names = (
        "event_to_provider_ms",
        "provider_to_ingest_ms",
        "ingest_to_normalize_ms",
        "normalize_to_feature_ms",
        "feature_to_inference_ms",
        "inference_to_market_ms",
        "market_to_signal_ms",
        "signal_to_visible_ms",
    )
    stage_columns = list(zip(*(_stage_values(s) for s in samples)))
    stage_p95 = {name: _pct(values, .95) for name, values in zip(stage_names, stage_columns)}
    stage_p99 = {name: _pct(values, .99) for name, values in zip(stage_names, stage_columns)}

    closed_on_arrival = [s.timing.entry_window_remaining_ms <= 0 for s in samples]
    processing_missed = [
        s.timing.entry_window_remaining_ms > 0 and s.timing.end_to_end_ms > s.timing.entry_window_remaining_ms
        for s in samples
    ]
    too_late = [a or b for a, b in zip(closed_on_arrival, processing_missed)]
    stale = [s.timing.end_to_end_ms > stale_threshold_ms for s in samples]

    predicted_entry = [s.predicted_state == "ENTRY" for s in samples]
    oracle = [bool(s.oracle_entry_eligible) for s in samples]
    fp = sum(p and not y for p, y in zip(predicted_entry, oracle))
    fn = sum((not p) and y for p, y in zip(predicted_entry, oracle))
    predicted_positive = sum(predicted_entry)
    actual_positive = sum(oracle)

    return {
        "sport": samples[0].sport,
        "market": samples[0].market,
        "n": len(samples),
        "modes": tuple(sorted({s.mode for s in samples})),
        "p50_ms": _pct(e2e, .50),
        "p95_ms": _pct(e2e, .95),
        "p99_ms": _pct(e2e, .99),
        "stage_p95_ms": stage_p95,
        "stage_p99_ms": stage_p99,
        "window_closed_on_arrival_rate": sum(closed_on_arrival) / len(samples),
        "processing_missed_window_rate": sum(processing_missed) / len(samples),
        "missed_window_rate": sum(too_late) / len(samples),
        "stale_signal_rate": sum(stale) / len(samples),
        "decision_too_late_rate": sum(too_late) / len(samples),
        "false_positive_count": fp,
        "false_negative_count": fn,
        "false_positive_rate": fp / predicted_positive if predicted_positive else 0.0,
        "false_negative_rate": fn / actual_positive if actual_positive else 0.0,
        "predicted_entry_count": predicted_positive,
        "oracle_entry_count": actual_positive,
    }


def live_slo_gate(report: dict[str, object], policy: LiveSLOPolicy) -> dict[str, object]:
    reasons: list[str] = []
    if int(report["n"]) < policy.minimum_samples:
        reasons.append("INSUFFICIENT_SAMPLE")
    modes = set(report["modes"])
    if policy.require_shadow and "SHADOW" not in modes:
        reasons.append("SHADOW_EVIDENCE_REQUIRED")
    if float(report["p95_ms"]) > policy.maximum_p95_ms:
        reasons.append("P95_LATENCY_BREACH")
    if float(report["p99_ms"]) > policy.maximum_p99_ms:
        reasons.append("P99_LATENCY_BREACH")
    for field, maximum, code in (
        ("missed_window_rate", policy.maximum_missed_window_rate, "MISSED_WINDOW_RATE_BREACH"),
        ("stale_signal_rate", policy.maximum_stale_signal_rate, "STALE_SIGNAL_RATE_BREACH"),
        ("decision_too_late_rate", policy.maximum_decision_too_late_rate, "DECISION_TOO_LATE_RATE_BREACH"),
        ("false_positive_rate", policy.maximum_false_positive_rate, "FALSE_POSITIVE_RATE_BREACH"),
        ("false_negative_rate", policy.maximum_false_negative_rate, "FALSE_NEGATIVE_RATE_BREACH"),
    ):
        if float(report[field]) > maximum:
            reasons.append(code)
    return {"pass": not reasons, "reasons": tuple(reasons)}


def grouped_live_reports(samples: Iterable[LiveValidationSample], *, stale_threshold_ms: float) -> dict[tuple[str, str], dict[str, object]]:
    groups: dict[tuple[str, str], list[LiveValidationSample]] = {}
    for sample in samples:
        groups.setdefault((sample.sport, sample.market), []).append(sample)
    return {key: live_validation_report(group, stale_threshold_ms=stale_threshold_ms) for key, group in sorted(groups.items())}
