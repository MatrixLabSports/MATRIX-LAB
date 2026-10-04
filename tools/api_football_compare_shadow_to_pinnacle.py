from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from app.application.football.odds_runtime import assess_odds_quote
from app.research.football.odds_ledger import FootballOddsLedger, FootballOddsQuote
from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle


COMPARISON_ROLE = "DIAGNOSTIC_REFERENCE_ONLY"
MODEL_ROLE_REQUIRED = "RESEARCH_SHADOW_BASELINE"
MODEL_STATUS_REQUIRED = "EXPERIMENTAL_NOT_PROMOTED"


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _parse_total_selection(selection: str) -> tuple[str, float] | None:
    match = re.search(r"(?i)\b(over|under)\b\s*([0-9]+(?:\.[0-9]+)?)", str(selection))
    if not match:
        return None
    return match.group(1).casefold(), float(match.group(2))


def _match_winner_side(selection: str, *, home_name: str, away_name: str) -> str | None:
    value = _norm(selection)
    if value in {"home", "1"} or value == _norm(home_name):
        return "home_win"
    if value in {"draw", "x"}:
        return "draw"
    if value in {"away", "2"} or value == _norm(away_name):
        return "away_win"
    return None


def _quote_rejection_reasons(
    quote: FootballOddsQuote,
    *,
    freeze: datetime,
    kickoff: datetime,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if quote.bookmaker.casefold() != "pinnacle":
        reasons.append("not_pinnacle")
    if quote.quote_role != "REFERENCE":
        reasons.append("not_reference")
    if quote.phase != "PREMATCH":
        reasons.append("not_prematch")
    if quote.quoted_at > freeze:
        reasons.append("quoted_after_shadow_freeze")
    if quote.captured_at > freeze:
        reasons.append("captured_after_shadow_freeze")
    if quote.quoted_at >= kickoff:
        reasons.append("quoted_at_or_after_kickoff")
    if quote.captured_at >= kickoff:
        reasons.append("captured_at_or_after_kickoff")
    if not reasons:
        reasons.extend(assess_odds_quote(quote).blocked_reasons)
    return tuple(dict.fromkeys(reasons))


def _quote_before_freeze(
    quote: FootballOddsQuote,
    *,
    freeze: datetime,
    kickoff: datetime,
) -> bool:
    return not _quote_rejection_reasons(quote, freeze=freeze, kickoff=kickoff)


def _latest_by_key(
    quotes: list[tuple[int, str, FootballOddsQuote]],
    key_fn,
) -> dict[Any, tuple[int, str, FootballOddsQuote]]:
    selected: dict[Any, tuple[int, str, FootballOddsQuote]] = {}
    for item in quotes:
        key = key_fn(item[2])
        if key is None:
            continue
        current = selected.get(key)
        if current is None or (item[2].quoted_at, item[2].captured_at, item[0]) > (
            current[2].quoted_at,
            current[2].captured_at,
            current[0],
        ):
            selected[key] = item
    return selected


def compare_shadow_to_pinnacle(
    *,
    shadow: Mapping[str, Any],
    canonical_bundle: Mapping[str, Any],
    canonical_manifest: Mapping[str, Any],
    ledger: FootballOddsLedger,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if shadow.get("model_role") != MODEL_ROLE_REQUIRED:
        raise ValueError("SHADOW_MODEL_ROLE_MISMATCH")
    if shadow.get("model_status") != MODEL_STATUS_REQUIRED:
        raise ValueError("SHADOW_MODEL_STATUS_MISMATCH")
    if shadow.get("p_matrix_status") != "NOT_GENERATED":
        raise ValueError("P_MATRIX_MUST_REMAIN_NOT_GENERATED")
    protections = shadow.get("protections")
    if not isinstance(protections, Mapping):
        raise ValueError("SHADOW_PROTECTIONS_MISSING")
    if protections.get("odds_used_to_generate_probability") is not False:
        raise ValueError("SHADOW_PROBABILITY_MUST_BE_ODDS_INDEPENDENT")
    if protections.get("outcomes_used_to_generate_probability") is not False:
        raise ValueError("SHADOW_PROBABILITY_MUST_BE_OUTCOME_INDEPENDENT")
    if protections.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")
    if shadow.get("source_canonical_bundle_sha256") != canonical_manifest.get("bundle_sha256"):
        raise ValueError("SHADOW_CANONICAL_SHA_MISMATCH")
    if shadow.get("source_canonical_analysis_as_of_utc") != canonical_manifest.get("analysis_as_of_utc"):
        raise ValueError("SHADOW_CANONICAL_AS_OF_MISMATCH")

    canonical_by_fixture: dict[str, Mapping[str, Any]] = {}
    for raw in canonical_bundle.get("inputs", []):
        if isinstance(raw, Mapping):
            canonical_by_fixture[str(raw.get("fixture_id"))] = raw

    entries = ledger.load(verify=True)
    quote_items = [(entry.sequence, entry.entry_sha256, entry.quote) for entry in entries]
    ledger_fixture_ids = {item[2].fixture_id for item in quote_items}

    rows: list[dict[str, Any]] = []
    fixture_with_reference: set[str] = set()
    accepted_quote_count = 0
    mappable_quote_count = 0
    rejected_freshness_count = 0
    rejection_reason_counts: dict[str, int] = {}
    relevant_capture_delays: list[int] = []

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
        markets = shadow_row.get("markets")
        if not isinstance(markets, Mapping):
            raise ValueError(f"SHADOW_MARKETS_MISSING:{fixture_id}")

        fixture_items: list[tuple[int, str, FootballOddsQuote]] = []
        for item in quote_items:
            quote = item[2]
            if quote.fixture_id != fixture_id:
                continue
            if not (
                quote.bookmaker.casefold() == "pinnacle"
                and quote.quote_role == "REFERENCE"
                and quote.phase == "PREMATCH"
            ):
                continue
            relevant_capture_delays.append(int((quote.captured_at - quote.quoted_at).total_seconds()))
            rejection_reasons = _quote_rejection_reasons(quote, freeze=freeze, kickoff=kickoff)
            if not rejection_reasons:
                fixture_items.append(item)
                accepted_quote_count += 1
            else:
                rejected_freshness_count += 1
                for reason in rejection_reasons:
                    rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1

        match_latest = _latest_by_key(
            [item for item in fixture_items if item[2].market_key == "match_winner"],
            lambda q: _match_winner_side(q.selection_key, home_name=home_name, away_name=away_name),
        )
        total_latest = _latest_by_key(
            [item for item in fixture_items if item[2].market_key == "total_goals"],
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
                total_overround[line] = 1.0 / over[2].decimal_odds + 1.0 / under[2].decimal_odds

        candidates: list[tuple[str, tuple[int, str, FootballOddsQuote], float | None]] = []
        for market_key in ("home_win", "draw", "away_win"):
            item = match_latest.get(market_key)
            if item is not None and market_key in markets:
                candidates.append((market_key, item, match_overround))
        for line, market_key in ((1.5, "over_1_5"), (2.5, "over_2_5"), (3.5, "over_3_5")):
            item = total_latest.get(("over", line))
            if item is not None and market_key in markets:
                candidates.append((market_key, item, total_overround.get(line)))

        for shadow_market, item, overround in candidates:
            sequence, entry_sha, quote = item
            mappable_quote_count += 1
            fixture_with_reference.add(fixture_id)
            raw_implied = 1.0 / quote.decimal_odds
            vig_adjusted = None
            if overround is not None and overround > 0:
                vig_adjusted = raw_implied / overround
            model_probability = float(markets[shadow_market])
            reference_probability = vig_adjusted if vig_adjusted is not None else raw_implied
            rows.append({
                "fixture_id": fixture_id,
                "target_key": shadow_row.get("target_key"),
                "kickoff_utc": shadow_row.get("kickoff_utc"),
                "freeze_at_utc": shadow_row.get("freeze_at_utc"),
                "home_team_name": home_name,
                "away_team_name": away_name,
                "shadow_market": shadow_market,
                "shadow_probability": round(model_probability, 10),
                "shadow_probability_role": "RESEARCH_ONLY_NOT_P_MATRIX",
                "pinnacle_market_key": quote.market_key,
                "pinnacle_selection_key": quote.selection_key,
                "pinnacle_decimal_odds": quote.decimal_odds,
                "pinnacle_raw_implied_probability": round(raw_implied, 10),
                "pinnacle_overround": None if overround is None else round(overround, 10),
                "pinnacle_vig_adjusted_probability": None if vig_adjusted is None else round(vig_adjusted, 10),
                "diagnostic_probability_gap": round(model_probability - reference_probability, 10),
                "quoted_at_utc": quote.quoted_at.isoformat(),
                "captured_at_utc": quote.captured_at.isoformat(),
                "quote_age_seconds_at_freeze": int((freeze - quote.quoted_at).total_seconds()),
                "capture_delay_seconds": int((quote.captured_at - quote.quoted_at).total_seconds()),
                "quote_role": quote.quote_role,
                "comparison_role": COMPARISON_ROLE,
                "ledger_sequence": sequence,
                "ledger_entry_sha256": entry_sha,
                "source_payload_sha256": quote.source_payload_sha256,
                "decision": "NO_BET",
            })

    rows.sort(key=lambda row: (row["kickoff_utc"], row["fixture_id"], row["shadow_market"]))
    shadow_fixture_ids = {str(row.get("fixture_id")) for row in shadow.get("rows", []) if isinstance(row, Mapping)}

    comparison = {
        "schema": "MATRIX_FOOTBALL_SHADOW_PINNACLE_DIAGNOSTIC_V1",
        "comparison_role": COMPARISON_ROLE,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "shadow_freeze_at_utc": shadow.get("freeze_at_utc"),
        "source_canonical_bundle_sha256": canonical_manifest.get("bundle_sha256"),
        "source_shadow_model": shadow.get("model_name"),
        "source_shadow_model_status": shadow.get("model_status"),
        "source_shadow_model_role": shadow.get("model_role"),
        "p_matrix_status": "NOT_GENERATED",
        "shadow_fixture_count": len(shadow_fixture_ids),
        "pinnacle_ledger_fixture_count": len(ledger_fixture_ids),
        "matched_fixture_count": len(fixture_with_reference),
        "comparison_row_count": len(rows),
        "accepted_pinnacle_quote_observations_scanned": accepted_quote_count,
        "mappable_latest_reference_count": mappable_quote_count,
        "rejected_pinnacle_quote_observations": rejected_freshness_count,
        "rejection_reason_counts": dict(sorted(rejection_reason_counts.items())),
        "capture_delay_seconds_summary": {
            "count": len(relevant_capture_delays),
            "min": min(relevant_capture_delays) if relevant_capture_delays else None,
            "median": median(relevant_capture_delays) if relevant_capture_delays else None,
            "max": max(relevant_capture_delays) if relevant_capture_delays else None,
            "policy_max_prematch": 120,
        },
        "rows": rows,
        "protections": {
            "odds_used_to_generate_shadow_probability": False,
            "outcomes_used_to_generate_shadow_probability": False,
            "reference_is_diagnostic_only": True,
            "reference_does_not_promote_model": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

    manifest = {
        "schema": "MATRIX_FOOTBALL_SHADOW_PINNACLE_DIAGNOSTIC_MANIFEST_V1",
        "status": "PASS",
        "comparison_role": COMPARISON_ROLE,
        "shadow_fixture_count": comparison["shadow_fixture_count"],
        "matched_fixture_count": comparison["matched_fixture_count"],
        "comparison_row_count": comparison["comparison_row_count"],
        "pinnacle_ledger_fixture_count": comparison["pinnacle_ledger_fixture_count"],
        "accepted_pinnacle_quote_observations_scanned": accepted_quote_count,
        "mappable_latest_reference_count": mappable_quote_count,
        "rejected_pinnacle_quote_observations": rejected_freshness_count,
        "rejection_reason_counts": comparison["rejection_reason_counts"],
        "capture_delay_seconds_summary": comparison["capture_delay_seconds_summary"],
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
    raw = json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(raw, encoding="utf-8")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError(f"COMPARISON_ARTIFACT_TOO_LARGE_FOR_SECRET_SCAN:{path}")


def main() -> None:
    canonical_root = Path("evidence/api_football/canonical_analysis")
    canonical_bundle, canonical_manifest = load_chunked_canonical_bundle(canonical_root)
    shadow = _load(Path("evidence/api_football/experimental_shadow/shadow_freeze.json"))
    ledger = FootballOddsLedger(
        Path("evidence/api_football/pinnacle_reference/pinnacle_reference_odds.jsonl")
    )
    comparison, manifest = compare_shadow_to_pinnacle(
        shadow=shadow,
        canonical_bundle=canonical_bundle,
        canonical_manifest=canonical_manifest,
        ledger=ledger,
    )
    out = Path("evidence/api_football/pinnacle_shadow_comparison")
    _write(out / "comparison.json", comparison)
    _write(out / "manifest.json", manifest)
    print(json.dumps({
        "shadow_fixture_count": manifest["shadow_fixture_count"],
        "matched_fixture_count": manifest["matched_fixture_count"],
        "comparison_row_count": manifest["comparison_row_count"],
        "accepted_pinnacle_quote_observations_scanned": manifest["accepted_pinnacle_quote_observations_scanned"],
        "rejected_pinnacle_quote_observations": manifest["rejected_pinnacle_quote_observations"],
        "p_matrix_status": manifest["p_matrix_status"],
        "real_money": manifest["real_money"],
        "status": manifest["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
