from datetime import datetime, timedelta, timezone

from app.research.football.odds_ledger import FootballOddsLedger, FootballOddsQuote
from tools.api_football_compare_shadow_to_pinnacle_nominal_cadence import (
    compare_shadow_to_nominal_cadence_snapshots,
)
from tools.api_football_pinnacle_snapshot_age_audit import (
    API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS,
)


UTC = timezone.utc


def _quote(market: str, selection: str, odds: float, age_seconds: int) -> FootballOddsQuote:
    captured = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    return FootballOddsQuote(
        provider="api_football",
        provider_event_id="900",
        fixture_id="900",
        bookmaker="Pinnacle",
        market_key=market,
        selection_key=selection,
        decimal_odds=odds,
        quoted_at=captured - timedelta(seconds=age_seconds),
        captured_at=captured,
        phase="PREMATCH",
        quote_role="REFERENCE",
        source_payload_sha256="a" * 64,
        source_reference=f"test:{market}:{selection}",
    )


def _inputs():
    canonical_sha = "b" * 64
    canonical = {
        "inputs": [{
            "fixture_id": "900",
            "home_team_name": "Home FC",
            "away_team_name": "Away FC",
        }]
    }
    manifest = {"bundle_sha256": canonical_sha}
    shadow = {
        "model_name": "transparent_poisson_baseline_v1",
        "model_role": "RESEARCH_SHADOW_BASELINE",
        "model_status": "EXPERIMENTAL_NOT_PROMOTED",
        "p_matrix_status": "NOT_GENERATED",
        "source_canonical_bundle_sha256": canonical_sha,
        "protections": {
            "odds_used_to_generate_probability": False,
            "outcomes_used_to_generate_probability": False,
            "real_money": "BLOCKED",
        },
        "rows": [{
            "fixture_id": "900",
            "target_key": "api_football:fixture:900",
            "kickoff_utc": "2026-09-28T18:00:00+00:00",
            "freeze_at_utc": "2026-09-28T12:01:00+00:00",
            "markets": {
                "home_win": 0.50,
                "draw": 0.25,
                "away_win": 0.25,
                "over_1_5": 0.80,
                "over_2_5": 0.60,
                "over_3_5": 0.35,
                "btts": 0.55,
            },
        }],
    }
    return canonical, manifest, shadow


def test_nominal_cadence_comparison_is_research_only_and_not_clv(tmp_path):
    canonical, manifest, shadow = _inputs()
    ledger = FootballOddsLedger(tmp_path / "odds.jsonl")
    age = 3600
    ledger.append_many([
        _quote("match_winner", "Home", 2.0, age),
        _quote("match_winner", "Draw", 3.4, age),
        _quote("match_winner", "Away", 4.0, age),
        _quote("total_goals", "Over 2.5", 1.9, age),
        _quote("total_goals", "Under 2.5", 1.9, age),
    ])

    comparison, result = compare_shadow_to_nominal_cadence_snapshots(
        shadow=shadow,
        canonical_bundle=canonical,
        canonical_manifest=manifest,
        ledger=ledger,
    )

    assert result["status"] == "PASS"
    assert result["comparison_role"] == "RESEARCH_SNAPSHOT_REFERENCE_ONLY"
    assert result["matched_fixture_count"] == 1
    assert result["fixtures_with_at_least_3_mapped_reference_markets"] == 1
    assert result["comparison_row_count"] == 4
    assert result["strict_120s_fresh_gate_changed"] is False
    assert result["closing_reference_status"] == "NOT_ESTABLISHED_FROM_NOMINAL_CADENCE_SNAPSHOTS"
    assert result["execution_reference_status"] == "NOT_ESTABLISHED"
    assert result["clv_status"] == "NOT_ELIGIBLE"
    assert result["p_matrix_status"] == "NOT_GENERATED"
    assert result["odds_used_to_generate_shadow_probability"] is False
    assert result["real_money"] == "BLOCKED"

    assert all(row["is_closing_reference"] is False for row in comparison["rows"])
    assert all(row["is_execution_reference"] is False for row in comparison["rows"])
    assert all(row["eligible_for_clv"] is False for row in comparison["rows"])
    assert all(row["decision"] == "NO_BET" for row in comparison["rows"])
    assert all(row["snapshot_age_class"] == "WITHIN_DOCUMENTED_3H_CADENCE" for row in comparison["rows"])


def test_snapshot_older_than_documented_cadence_is_not_compared(tmp_path):
    canonical, manifest, shadow = _inputs()
    ledger = FootballOddsLedger(tmp_path / "odds.jsonl")
    ledger.append(
        _quote(
            "match_winner",
            "Home",
            2.0,
            API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS + 1,
        )
    )

    comparison, result = compare_shadow_to_nominal_cadence_snapshots(
        shadow=shadow,
        canonical_bundle=canonical,
        canonical_manifest=manifest,
        ledger=ledger,
    )

    assert result["matched_fixture_count"] == 0
    assert result["comparison_row_count"] == 0
    assert comparison["rows"] == []
