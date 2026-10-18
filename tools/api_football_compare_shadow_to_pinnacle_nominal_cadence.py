from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from app.application.football.odds_runtime import FootballOddsSourcePolicy, assess_odds_quote
from app.research.football.odds_ledger import FootballOddsLedger, FootballOddsQuote
from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.api_football_compare_shadow_to_pinnacle import (
    _latest_by_key,
    _match_winner_side,
    _parse_total_selection,
)
from tools.api_football_pinnacle_snapshot_age_audit import (
    API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS,
    DOCUMENTATION_DATE,
    DOCUMENTATION_URL,
)


COMPARISON_ROLE = "RESEARCH_SNAPSHOT_REFERENCE_ONLY"
SNAPSHOT_POLICY = FootballOddsSourcePolicy(
    max_prematch_capture_delay_seconds=API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS,
)


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _eligible_snapshot(
    quote: FootballOddsQuote,
    *,
    freeze: datetime,
    kickoff: datetime,
) -> bool:
    if quote.bookmaker.casefold() != "pinnacle":
        return False
    if quote.quote_role != "REFERENCE" or quote.phase != "PREMATCH":
        return False
    if quote.quoted_at > freeze or quote.captured_at > freeze:
        return False
    if quote.quoted_at >= kickoff or quote.captured_at >= kickoff:
        return False
    return assess_odds_quote(quote, policy=SNAPSHOT_POLICY).accepted


def compare_shadow_to_nominal_cadence_snapshots(
    *,
    shadow: Mapping[str, Any],
    canonical_bundle: Mapping[str, Any],
    canonical_manifest: Mapping[str, Any],
    ledger: FootballOddsLedger,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if shadow.get("model_role") != "RESEARCH_SHADOW_BASELINE":
        raise ValueError("SHADOW_MODEL_ROLE_MISMATCH")
    if shadow.get("model_status") != "EXPERIMENTAL_NOT_PROMOTED":
        raise ValueError("SHADOW_MODEL_STATUS_MISMATCH")
    if shadow.get("p_matrix_status") != "NOT_GENERATED":
        raise ValueError("P_MATRIX_MUST_REMAIN_NOT_GENERATED")
    protections = shadow.get("protections")
    if not isinstance(protections, Mapping):
        raise ValueError("SHADOW_PROTECTIONS_MISSING")
    if protections.get("odds_used_to_generate_probability") is not False:
        raise ValueError("ODDS_MUST_NOT_GENERATE_SHADOW_PROBABILITY")
    if protections.get("outcomes_used_to_generate_probability") is not False:
        raise ValueError("OUTCOMES_MUST_NOT_GENERATE_SHADOW_PROBABILITY")
    if protections.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")
    if shadow.get("source_canonical_bundle_sha256") != canonical_manifest.get("bundle_sha256"):
        raise ValueError("SHADOW_CANONICAL_SHA_MISMATCH")

    canonical_by_fixture = {
        str(row.get("fixture_id")): row
        for row in canonical_bundle.get("inputs", [])
        if isinstance(row, Mapping)
    }
    entries = ledger.load(verify=True)
    quote_items = [(entry.sequence, entry.entry_sha256, entry.quote) for entry in entries]

    rows: list[dict[str, Any]] = []
    matched_fixtures: set[str] = set()
    fixtures_with_three_or_more_markets: set[str] = set()
    markets_per_fixture: dict[str, int] = {}

    for shadow_row in shadow.get("rows", []):
        if not isinstance(shadow_row, Mapping):
            continue
        fixture_id = str(shadow_row.get("fixture_id"))
        canonical = canonical_by_fixture.get(fixture_id)
        if canonical is None:
            raise ValueError(f"SHADOW_FIXTURE_NOT_IN_CANONICAL:{fixture_id}")

        freeze = _utc(shadow_row["freeze_at_utc"])
        kickoff = _utc(shadow_row["kickoff_utc"])
        home_name = str(canonical.get("home_team_name") or "")
        away_name = str(canonical.get("away_team_name") or "")
        shadow_markets = shadow_row.get("markets")
        if not isinstance(shadow_markets, Mapping):
            raise ValueError(f"SHADOW_MARKETS_MISSING:{fixture_id}")

        eligible_items = [
            item
            for item in quote_items
            if item[2].fixture_id == fixture_id
            and _eligible_snapshot(item[2], freeze=freeze, kickoff=kickoff)
        ]

        match_latest = _latest_by_key(
            [item for item in eligible_items if item[2].market_key == "match_winner"],
            lambda q: _match_winner_side(
                q.selection_key,
                home_name=home_name,
                away_name=away_name,
            ),
        )
        total_latest = _latest_by_key(
            [item for item in eligible_items if item[2].market_key == "total_goals"],
            lambda q: _parse_total_selection(q.selection_key),
        )

        match_overround = None
        if set(match_latest) >= {"home_win", "draw", "away_win"}:
            match_overround = sum(
                1.0 / match_latest[key][2].decimal_odds
                for key in ("home_win", "draw", "away_win")
            )

        total_overround: dict[float, float] = {}
        for line in (1.5, 2.5, 3.5):
            over = total_latest.get(("over", line))
            under = total_latest.get(("under", line))
            if over is not None and under is not None:
                total_overround[line] = (
                    1.0 / over[2].decimal_odds + 1.0 / under[2].decimal_odds
                )

        candidates: list[tuple[str, tuple[int, str, FootballOddsQuote], float | None]] = []
        for shadow_market in ("home_win", "draw", "away_win"):
            item = match_latest.get(shadow_market)
            if item is not None and shadow_market in shadow_markets:
                candidates.append((shadow_market, item, match_overround))
        for line, shadow_market in (
            (1.5, "over_1_5"),
            (2.5, "over_2_5"),
            (3.5, "over_3_5"),
        ):
            item = total_latest.get(("over", line))
            if item is not None and shadow_market in shadow_markets:
                candidates.append((shadow_market, item, total_overround.get(line)))

        fixture_market_count = 0
        for shadow_market, item, overround in candidates:
            sequence, entry_sha, quote = item
            raw_implied = 1.0 / quote.decimal_odds
            vig_adjusted = None
            if overround is not None and overround > 0:
                vig_adjusted = raw_implied / overround
            reference_probability = vig_adjusted if vig_adjusted is not None else raw_implied
            shadow_probability = float(shadow_markets[shadow_market])
            source_snapshot_age = int((quote.captured_at - quote.quoted_at).total_seconds())

            rows.append({
                "fixture_id": fixture_id,
                "target_key": shadow_row.get("target_key"),
                "kickoff_utc": shadow_row.get("kickoff_utc"),
                "freeze_at_utc": shadow_row.get("freeze_at_utc"),
                "home_team_name": home_name,
                "away_team_name": away_name,
                "shadow_market": shadow_market,
                "shadow_probability": round(shadow_probability, 10),
                "shadow_probability_role": "RESEARCH_ONLY_NOT_P_MATRIX",
                "pinnacle_market_key": quote.market_key,
                "pinnacle_selection_key": quote.selection_key,
                "pinnacle_decimal_odds": quote.decimal_odds,
                "pinnacle_raw_implied_probability": round(raw_implied, 10),
                "pinnacle_overround": None if overround is None else round(overround, 10),
                "pinnacle_vig_adjusted_probability": (
                    None if vig_adjusted is None else round(vig_adjusted, 10)
                ),
                "diagnostic_probability_gap": round(
                    shadow_probability - reference_probability,
                    10,
                ),
                "quoted_at_utc": quote.quoted_at.isoformat(),
                "captured_at_utc": quote.captured_at.isoformat(),
                "source_snapshot_age_seconds": source_snapshot_age,
                "source_snapshot_age_minutes": round(source_snapshot_age / 60.0, 3),
                "snapshot_age_class": "WITHIN_DOCUMENTED_3H_CADENCE",
                "comparison_role": COMPARISON_ROLE,
                "is_strict_fresh_reference": source_snapshot_age <= 120,
                "is_closing_reference": False,
                "is_execution_reference": False,
                "eligible_for_clv": False,
                "ledger_sequence": sequence,
                "ledger_entry_sha256": entry_sha,
                "source_payload_sha256": quote.source_payload_sha256,
                "decision": "NO_BET",
            })
            fixture_market_count += 1
            matched_fixtures.add(fixture_id)

        markets_per_fixture[fixture_id] = fixture_market_count
        if fixture_market_count >= 3:
            fixtures_with_three_or_more_markets.add(fixture_id)

    rows.sort(key=lambda row: (row["kickoff_utc"], row["fixture_id"], row["shadow_market"]))
    matched_counts = [markets_per_fixture[fid] for fid in matched_fixtures]

    comparison = {
        "schema": "MATRIX_FOOTBALL_SHADOW_PINNACLE_NOMINAL_CADENCE_COMPARISON_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "comparison_role": COMPARISON_ROLE,
        "provider_documentation": {
            "url": DOCUMENTATION_URL,
            "published_date": DOCUMENTATION_DATE,
            "documented_prematch_odds_update_seconds": (
                API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS
            ),
        },
        "source_shadow_model": shadow.get("model_name"),
        "source_shadow_model_status": shadow.get("model_status"),
        "source_shadow_model_role": shadow.get("model_role"),
        "source_canonical_bundle_sha256": canonical_manifest.get("bundle_sha256"),
        "p_matrix_status": "NOT_GENERATED",
        "shadow_fixture_count": len(shadow.get("rows", [])),
        "matched_fixture_count": len(matched_fixtures),
        "fixtures_with_at_least_3_mapped_reference_markets": len(
            fixtures_with_three_or_more_markets
        ),
        "comparison_row_count": len(rows),
        "mapped_markets_per_matched_fixture": {
            "min": min(matched_counts) if matched_counts else 0,
            "max": max(matched_counts) if matched_counts else 0,
        },
        "rows": rows,
        "protections": {
            "strict_120s_fresh_gate_changed": False,
            "snapshots_are_closing_reference": False,
            "snapshots_are_execution_reference": False,
            "snapshots_are_eligible_for_clv": False,
            "odds_used_to_generate_shadow_probability": False,
            "outcomes_used_to_generate_shadow_probability": False,
            "model_promotion": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

    manifest = {
        "schema": "MATRIX_FOOTBALL_SHADOW_PINNACLE_NOMINAL_CADENCE_COMPARISON_MANIFEST_V1",
        "status": "PASS",
        "comparison_role": COMPARISON_ROLE,
        "documented_provider_cadence_seconds": (
            API_FOOTBALL_DOCUMENTED_PREMATCH_UPDATE_SECONDS
        ),
        "strict_120s_fresh_gate_changed": False,
        "shadow_fixture_count": comparison["shadow_fixture_count"],
        "matched_fixture_count": comparison["matched_fixture_count"],
        "fixtures_with_at_least_3_mapped_reference_markets": comparison[
            "fixtures_with_at_least_3_mapped_reference_markets"
        ],
        "comparison_row_count": comparison["comparison_row_count"],
        "mapped_markets_per_matched_fixture": comparison[
            "mapped_markets_per_matched_fixture"
        ],
        "closing_reference_status": "NOT_ESTABLISHED_FROM_NOMINAL_CADENCE_SNAPSHOTS",
        "execution_reference_status": "NOT_ESTABLISHED",
        "clv_status": "NOT_ELIGIBLE",
        "p_matrix_status": "NOT_GENERATED",
        "odds_used_to_generate_shadow_probability": False,
        "model_promotion": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    return comparison, manifest


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
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError(f"COMPARISON_ARTIFACT_TOO_LARGE_FOR_SECRET_SCAN:{path}")


def main() -> None:
    root = Path("evidence/api_football")
    canonical_bundle, canonical_manifest = load_chunked_canonical_bundle(
        root / "canonical_analysis"
    )
    comparison, manifest = compare_shadow_to_nominal_cadence_snapshots(
        shadow=_load(root / "experimental_shadow" / "shadow_freeze.json"),
        canonical_bundle=canonical_bundle,
        canonical_manifest=canonical_manifest,
        ledger=FootballOddsLedger(root / "pinnacle_reference" / "pinnacle_reference_odds.jsonl"),
    )
    out = root / "pinnacle_nominal_cadence_comparison"
    _write(out / "comparison.json", comparison)
    _write(out / "manifest.json", manifest)
    print(json.dumps({
        "matched_fixture_count": manifest["matched_fixture_count"],
        "fixtures_with_at_least_3_mapped_reference_markets": manifest[
            "fixtures_with_at_least_3_mapped_reference_markets"
        ],
        "comparison_row_count": manifest["comparison_row_count"],
        "mapped_markets_per_matched_fixture": manifest[
            "mapped_markets_per_matched_fixture"
        ],
        "strict_120s_fresh_gate_changed": manifest["strict_120s_fresh_gate_changed"],
        "p_matrix_status": manifest["p_matrix_status"],
        "real_money": manifest["real_money"],
        "status": manifest["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
