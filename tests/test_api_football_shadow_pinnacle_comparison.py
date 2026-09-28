from datetime import datetime, timezone

from app.research.football.odds_ledger import FootballOddsLedger, FootballOddsQuote
from tools.api_football_compare_shadow_to_pinnacle import compare_shadow_to_pinnacle


def _quote(
    *,
    fixture_id: str,
    market_key: str,
    selection_key: str,
    odds: float,
    quoted: str = "2026-09-28T11:58:00+00:00",
    captured: str = "2026-09-28T11:58:30+00:00",
) -> FootballOddsQuote:
    return FootballOddsQuote(
        provider="api_football",
        provider_event_id=fixture_id,
        fixture_id=fixture_id,
        bookmaker="Pinnacle",
        market_key=market_key,
        selection_key=selection_key,
        decimal_odds=odds,
        quoted_at=datetime.fromisoformat(quoted),
        captured_at=datetime.fromisoformat(captured),
        phase="PREMATCH",
        quote_role="REFERENCE",
        source_payload_sha256="a" * 64,
        source_reference=f"test:{fixture_id}:{market_key}:{selection_key}",
    )


def _canonical_and_shadow():
    sha = "b" * 64
    canonical = {
        "inputs": [
            {
                "fixture_id": "900",
                "home_team_name": "Home FC",
                "away_team_name": "Away FC",
            }
        ]
    }
    manifest = {
        "bundle_sha256": sha,
        "analysis_as_of_utc": "2026-09-28T11:50:00+00:00",
    }
    shadow = {
        "model_name": "transparent_poisson_baseline_v1",
        "model_role": "RESEARCH_SHADOW_BASELINE",
        "model_status": "EXPERIMENTAL_NOT_PROMOTED",
        "p_matrix_status": "NOT_GENERATED",
        "freeze_at_utc": "2026-09-28T12:00:00+00:00",
        "source_canonical_bundle_sha256": sha,
        "source_canonical_analysis_as_of_utc": manifest["analysis_as_of_utc"],
        "protections": {
            "odds_used_to_generate_probability": False,
            "outcomes_used_to_generate_probability": False,
            "real_money": "BLOCKED",
        },
        "rows": [
            {
                "fixture_id": "900",
                "target_key": "api_football:fixture:900",
                "kickoff_utc": "2026-09-28T18:00:00+00:00",
                "freeze_at_utc": "2026-09-28T12:00:00+00:00",
                "markets": {
                    "home_win": 0.50,
                    "draw": 0.25,
                    "away_win": 0.25,
                    "over_1_5": 0.80,
                    "over_2_5": 0.60,
                    "over_3_5": 0.35,
                    "btts": 0.55,
                },
            }
        ],
    }
    return canonical, manifest, shadow


def test_pinnacle_reference_is_joined_diagnostically_without_changing_shadow_probability(tmp_path):
    canonical, manifest, shadow = _canonical_and_shadow()
    ledger = FootballOddsLedger(tmp_path / "odds.jsonl")
    ledger.append_many(
        [
            _quote(fixture_id="900", market_key="match_winner", selection_key="Home", odds=2.0),
            _quote(fixture_id="900", market_key="match_winner", selection_key="Draw", odds=3.4),
            _quote(fixture_id="900", market_key="match_winner", selection_key="Away", odds=4.0),
            _quote(fixture_id="900", market_key="total_goals", selection_key="Over 2.5", odds=1.9),
            _quote(fixture_id="900", market_key="total_goals", selection_key="Under 2.5", odds=1.9),
        ]
    )

    comparison, result = compare_shadow_to_pinnacle(
        shadow=shadow,
        canonical_bundle=canonical,
        canonical_manifest=manifest,
        ledger=ledger,
    )

    assert result["status"] == "PASS"
    assert result["matched_fixture_count"] == 1
    assert result["comparison_row_count"] == 4
    assert result["p_matrix_status"] == "NOT_GENERATED"
    assert result["odds_used_to_generate_shadow_probability"] is False
    assert result["model_promotion"] is False
    assert result["real_money"] == "BLOCKED"

    rows = {row["shadow_market"]: row for row in comparison["rows"]}
    assert set(rows) == {"home_win", "draw", "away_win", "over_2_5"}
    assert rows["home_win"]["shadow_probability"] == 0.5
    assert rows["home_win"]["pinnacle_raw_implied_probability"] == 0.5
    assert rows["home_win"]["pinnacle_overround"] is not None
    assert rows["home_win"]["pinnacle_vig_adjusted_probability"] is not None
    assert rows["over_2_5"]["pinnacle_vig_adjusted_probability"] == 0.5
    assert all(row["decision"] == "NO_BET" for row in comparison["rows"])
    assert all(row["comparison_role"] == "DIAGNOSTIC_REFERENCE_ONLY" for row in comparison["rows"])


def test_quote_after_freeze_is_rejected(tmp_path):
    canonical, manifest, shadow = _canonical_and_shadow()
    ledger = FootballOddsLedger(tmp_path / "odds.jsonl")
    ledger.append(
        _quote(
            fixture_id="900",
            market_key="match_winner",
            selection_key="Home",
            odds=2.0,
            quoted="2026-09-28T12:01:00+00:00",
            captured="2026-09-28T12:01:30+00:00",
        )
    )

    comparison, result = compare_shadow_to_pinnacle(
        shadow=shadow,
        canonical_bundle=canonical,
        canonical_manifest=manifest,
        ledger=ledger,
    )

    assert result["matched_fixture_count"] == 0
    assert result["comparison_row_count"] == 0
    assert result["rejected_pinnacle_quote_observations"] == 1
    assert comparison["rows"] == []
