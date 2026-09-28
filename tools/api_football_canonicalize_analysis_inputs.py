from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from app.research.football.match_analysis_input import (
    assess_match_analysis_readiness,
    build_match_analysis_inputs_from_benchmark,
)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("ANALYSIS_AS_OF_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _parse_utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_canonical_analysis_bundle(
    *,
    benchmark: Mapping[str, Any],
    analysis_as_of: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if benchmark.get("provider") != "api_football":
        raise ValueError("PROVIDER_MISMATCH")
    if benchmark.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")
    if benchmark.get("money_decisions_enabled") is not False:
        raise ValueError("MONEY_DECISIONS_MUST_BE_DISABLED")

    fixtures = benchmark.get("fixtures")
    if not isinstance(fixtures, Mapping):
        raise ValueError("FIXTURES_MUST_BE_OBJECT")

    as_of = _aware_utc(analysis_as_of)
    as_of_text = as_of.isoformat()
    source_unresolved = {
        str(value)
        for value in benchmark.get("unresolved_targets", [])
        if str(value).strip()
    }

    not_future_targets: list[str] = []
    for target_key, raw in fixtures.items():
        if not isinstance(raw, Mapping):
            continue
        kickoff = raw.get("kickoff_utc")
        if kickoff is None:
            continue
        if _parse_utc(kickoff) <= as_of:
            not_future_targets.append(str(target_key))

    values, rejected = build_match_analysis_inputs_from_benchmark(
        benchmark,
        analysis_as_of_utc=as_of_text,
    )
    rejected_set = set(rejected)

    ready_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    for value in values:
        readiness = assess_match_analysis_readiness(value)
        blocked_reasons = list(readiness.missing_critical)
        if value.target_key in source_unresolved:
            blocked_reasons.append("SOURCE_UNRESOLVED_TARGET")

        row = asdict(value)
        row["canonical_sha256"] = value.canonical_sha256()
        row["readiness"] = asdict(readiness)

        if readiness.ready and not blocked_reasons:
            ready_rows.append(row)
        else:
            blocked_rows.append({
                "target_key": value.target_key,
                "fixture_id": value.fixture_id,
                "kickoff_utc": value.kickoff_utc,
                "home_history_count": readiness.home_history_count,
                "away_history_count": readiness.away_history_count,
                "missing_critical": sorted(set(blocked_reasons)),
                "warnings": list(readiness.warnings),
            })

    ready_rows.sort(key=lambda row: (row["kickoff_utc"], row["fixture_id"]))
    blocked_rows.sort(key=lambda row: (row["kickoff_utc"], row["fixture_id"]))
    not_future_targets = sorted(set(not_future_targets))

    bundle = {
        "schema": "MATRIX_API_FOOTBALL_CANONICAL_ANALYSIS_INPUTS_V1",
        "provider": "api_football",
        "benchmark_id": benchmark.get("benchmark_id"),
        "analysis_as_of_utc": as_of_text,
        "analysis_as_of_source": "RUNTIME_UTC_NOW",
        "source_fixture_capture_at_utc": benchmark.get("captured_at_utc"),
        "ready_input_count": len(ready_rows),
        "blocked_future_input_count": len(blocked_rows),
        "not_future_at_analysis_count": len(not_future_targets),
        "inputs": ready_rows,
        "blocked_future_inputs": blocked_rows,
        "not_future_targets": not_future_targets,
        "protections": {
            "identity_validated": True,
            "history_before_target_required": True,
            "history_observed_by_analysis_as_of_required": True,
            "analysis_strictly_before_kickoff_required": True,
            "odds_used_to_generate_model_probability": False,
            "model_probability_generated": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

    manifest = {
        "schema": "MATRIX_API_FOOTBALL_CANONICAL_ANALYSIS_INPUTS_MANIFEST_V1",
        "provider": "api_football",
        "status": "PASS",
        "benchmark_id": benchmark.get("benchmark_id"),
        "analysis_as_of_utc": as_of_text,
        "analysis_as_of_source": "RUNTIME_UTC_NOW",
        "source_fixture_capture_at_utc": benchmark.get("captured_at_utc"),
        "total_fixture_count": len(fixtures),
        "builder_output_count": len(values),
        "ready_input_count": len(ready_rows),
        "blocked_future_input_count": len(blocked_rows),
        "not_future_at_analysis_count": len(not_future_targets),
        "source_unresolved_target_count": len(source_unresolved),
        "rejected_target_count": len(rejected_set),
        "rejected_targets": sorted(rejected_set),
        "bundle_sha256": _canonical_hash(bundle),
        "model_probability_generated": False,
        "p_matrix_status": "NOT_GENERATED",
        "baseline_poisson_status": "EXPERIMENTAL_NOT_PROMOTED",
        "odds_used_to_generate_model_probability": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    return bundle, manifest


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    source = Path("evidence/api_football/team_last_fallback/benchmark_after_team_last.json")
    out = Path("evidence/api_football/canonical_analysis")
    analysis_as_of = datetime.now(timezone.utc).replace(microsecond=0)
    bundle, manifest = build_canonical_analysis_bundle(
        benchmark=_load(source),
        analysis_as_of=analysis_as_of,
    )
    _write(out / "canonical_inputs.json", bundle)
    _write(out / "manifest.json", manifest)
    print(json.dumps({
        "analysis_as_of_utc": manifest["analysis_as_of_utc"],
        "total_fixture_count": manifest["total_fixture_count"],
        "ready_input_count": manifest["ready_input_count"],
        "blocked_future_input_count": manifest["blocked_future_input_count"],
        "not_future_at_analysis_count": manifest["not_future_at_analysis_count"],
        "p_matrix_status": manifest["p_matrix_status"],
        "real_money": manifest["real_money"],
        "status": manifest["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
