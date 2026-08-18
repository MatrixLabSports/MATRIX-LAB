"""Provider-neutral supplemental pre-match evidence for MATRIX FÚTBOL.

This module exists for a narrow reason: a primary provider may resolve the target fixture
but the current subscription may not expose enough historical results for research. We
allow independently verified supplemental evidence *without silently pretending it came
from the primary provider*.

Rules:
- frozen API-Football fixture identity always wins and can never be overwritten;
- external target identity is accepted only for targets unresolved by the frozen benchmark;
- every supplemental result carries provider + source reference + observation timestamp;
- date-only historical sources remain date-only: MATRIX never invents a kickoff time;
- same-day date-only history is rejected conservatively;
- all source-record hashes are verified before a row can enter canonical analysis input.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any, Mapping

from app.research.football.match_analysis_input import (
    FootballHistoryObservation,
    FootballMatchAnalysisInput,
    _non_empty,
    _sha256_hex,
    _utc,
    build_match_analysis_inputs_from_benchmark,
)


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def supplemental_record_sha256(record: Mapping[str, Any]) -> str:
    """Hash a supplemental record excluding its own hash field."""
    payload = {key: value for key, value in record.items() if key != "source_record_sha256"}
    return _canonical_hash(payload)


def _verified_hash(record: Mapping[str, Any]) -> str:
    supplied = _sha256_hex(str(record.get("source_record_sha256") or ""), "source_record_sha256")
    computed = supplemental_record_sha256(record)
    if supplied != computed:
        raise ValueError("supplemental source_record_sha256 mismatch")
    return supplied


def _history_rows(
    raw_rows: Any,
    *,
    canonical_team_id: str,
    canonical_team_name: str,
    supplement_captured_at: str,
    target_kickoff_utc: str,
) -> tuple[FootballHistoryObservation, ...]:
    if not isinstance(raw_rows, list):
        return ()
    target_kickoff = _utc(target_kickoff_utc)
    captured_at = _utc(supplement_captured_at)
    if captured_at >= target_kickoff:
        raise ValueError("supplemental evidence was captured too late for target fixture")

    rows: list[FootballHistoryObservation] = []
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            raise ValueError("supplemental history row must be an object")
        record_hash = _verified_hash(raw)
        source_provider = _non_empty(raw.get("source_provider"), "source_provider")
        source_reference = _non_empty(raw.get("source_reference"), "source_reference")
        match_date = _non_empty(raw.get("match_date"), "match_date")
        opponent_name = _non_empty(raw.get("opponent_name"), "opponent_name")
        role = _non_empty(raw.get("venue_role"), "venue_role")
        identity_kind = str(raw.get("fixture_identity_kind") or "derived")
        source_fixture_id = raw.get("source_fixture_id")
        if source_fixture_id is not None:
            fixture_id = f"{source_provider}:{_non_empty(source_fixture_id, 'source_fixture_id')}"
            identity_kind = "provider"
        else:
            fixture_id = f"derived:{source_provider}:{record_hash[:24]}"
            identity_kind = "derived"
        gf = raw.get("goals_for")
        ga = raw.get("goals_against")
        if isinstance(gf, bool) or isinstance(ga, bool) or not isinstance(gf, int) or not isinstance(ga, int):
            raise ValueError("supplemental goals must be integers")
        rows.append(
            FootballHistoryObservation(
                fixture_id=fixture_id,
                kickoff_utc=None,
                match_date=match_date,
                time_precision="date",
                team_id=canonical_team_id,
                team_name=canonical_team_name,
                opponent_id=None,
                opponent_name=opponent_name,
                venue_role=role,
                goals_for=gf,
                goals_against=ga,
                competition=None if raw.get("competition") is None else str(raw.get("competition")),
                source_provider=source_provider,
                observed_at_utc=supplement_captured_at,
                source_payload_sha256=record_hash,
                fixture_identity_kind=identity_kind,
                source_team_id=None if raw.get("source_team_id") is None else str(raw.get("source_team_id")),
                source_opponent_id=None if raw.get("source_opponent_id") is None else str(raw.get("source_opponent_id")),
                source_reference=source_reference,
            )
        )
    rows.sort(key=lambda row: row.effective_match_date(), reverse=True)
    return tuple(rows)


def _external_fixture_input(
    *,
    benchmark_id: str,
    target_key: str,
    fixture: Mapping[str, Any],
    histories: Mapping[str, Any],
    supplement_captured_at: str,
) -> FootballMatchAnalysisInput:
    fixture_hash = _verified_hash(fixture)
    kickoff = _non_empty(fixture.get("kickoff_utc"), "fixture.kickoff_utc")
    if _utc(supplement_captured_at) >= _utc(kickoff):
        raise ValueError("external fixture identity was captured too late")
    home_id = _non_empty(fixture.get("home_team_id"), "fixture.home_team_id")
    away_id = _non_empty(fixture.get("away_team_id"), "fixture.away_team_id")
    home_name = _non_empty(fixture.get("home_team_name"), "fixture.home_team_name")
    away_name = _non_empty(fixture.get("away_team_name"), "fixture.away_team_name")
    return FootballMatchAnalysisInput(
        benchmark_id=benchmark_id,
        target_key=target_key,
        fixture_id=_non_empty(fixture.get("fixture_id"), "fixture.fixture_id"),
        as_of_utc=supplement_captured_at,
        kickoff_utc=kickoff,
        home_team_id=home_id,
        home_team_name=home_name,
        away_team_id=away_id,
        away_team_name=away_name,
        competition_id=None if fixture.get("competition_id") is None else str(fixture.get("competition_id")),
        competition_name=_non_empty(fixture.get("competition_name"), "fixture.competition_name"),
        season=None if fixture.get("season") is None else int(fixture.get("season")),
        round_name=None if fixture.get("round_name") is None else str(fixture.get("round_name")),
        venue_name=None if fixture.get("venue_name") is None else str(fixture.get("venue_name")),
        fixture_source_provider=_non_empty(fixture.get("source_provider"), "fixture.source_provider"),
        fixture_payload_sha256=fixture_hash,
        fixture_id_namespace=_non_empty(fixture.get("fixture_id_namespace"), "fixture.fixture_id_namespace"),
        home_team_id_namespace=_non_empty(fixture.get("home_team_id_namespace"), "fixture.home_team_id_namespace"),
        away_team_id_namespace=_non_empty(fixture.get("away_team_id_namespace"), "fixture.away_team_id_namespace"),
        home_history=_history_rows(
            histories.get("home"),
            canonical_team_id=home_id,
            canonical_team_name=home_name,
            supplement_captured_at=supplement_captured_at,
            target_kickoff_utc=kickoff,
        ),
        away_history=_history_rows(
            histories.get("away"),
            canonical_team_id=away_id,
            canonical_team_name=away_name,
            supplement_captured_at=supplement_captured_at,
            target_kickoff_utc=kickoff,
        ),
    )


def build_match_analysis_inputs_with_supplement(
    benchmark: Mapping[str, Any],
    supplement: Mapping[str, Any],
) -> tuple[tuple[FootballMatchAnalysisInput, ...], tuple[str, ...]]:
    """Build canonical inputs while preserving the frozen primary-provider boundary."""
    benchmark_id = _non_empty(benchmark.get("benchmark_id"), "benchmark_id")
    if _non_empty(supplement.get("benchmark_id"), "supplement.benchmark_id") != benchmark_id:
        raise ValueError("supplement benchmark_id mismatch")
    captured_at = _non_empty(supplement.get("captured_at_utc"), "supplement.captured_at_utc")
    _utc(captured_at)
    targets = supplement.get("targets")
    if not isinstance(targets, Mapping):
        raise ValueError("supplement targets must be an object")

    frozen_inputs, unresolved = build_match_analysis_inputs_from_benchmark(benchmark)
    by_key = {item.target_key: item for item in frozen_inputs}
    original_frozen_keys = set(by_key)

    for target_key, raw_target in targets.items():
        if not isinstance(raw_target, Mapping):
            raise ValueError("supplement target must be an object")
        histories = raw_target.get("histories") if isinstance(raw_target.get("histories"), Mapping) else {}
        if target_key in original_frozen_keys:
            # Never accept a supplemental fixture override for a target frozen by API-Football.
            if raw_target.get("fixture") is not None:
                raise ValueError("supplement cannot override frozen primary-provider fixture identity")
            current = by_key[target_key]
            by_key[target_key] = FootballMatchAnalysisInput(
                **{
                    **asdict(current),
                    "as_of_utc": captured_at,
                    "home_history": _history_rows(
                        histories.get("home"),
                        canonical_team_id=current.home_team_id,
                        canonical_team_name=current.home_team_name,
                        supplement_captured_at=captured_at,
                        target_kickoff_utc=current.kickoff_utc,
                    ),
                    "away_history": _history_rows(
                        histories.get("away"),
                        canonical_team_id=current.away_team_id,
                        canonical_team_name=current.away_team_name,
                        supplement_captured_at=captured_at,
                        target_kickoff_utc=current.kickoff_utc,
                    ),
                }
            )
        else:
            fixture = raw_target.get("fixture")
            if not isinstance(fixture, Mapping):
                continue
            by_key[target_key] = _external_fixture_input(
                benchmark_id=benchmark_id,
                target_key=str(target_key),
                fixture=fixture,
                histories=histories,
                supplement_captured_at=captured_at,
            )

    expected = set(str(k) for k in benchmark.get("fixtures", {}).keys())
    expected.update(str(k) for k in benchmark.get("unresolved_targets", []))
    still_unresolved = tuple(sorted(expected - set(by_key)))
    return tuple(by_key[key] for key in sorted(by_key)), still_unresolved
