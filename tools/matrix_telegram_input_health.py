"""Read-only health check for Telegram's canonical upstream inputs.

No provider calls, no secrets, no Telegram messages. Exit 2 when both sports
have no canonical JSON files for today/tomorrow (Bogotá).
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo



def _read_json(path: Path):
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else None
    except (OSError, UnicodeError, ValueError):
        return None


def _independent_gate_detail(intake: dict | None, shadow: dict | None, quote: dict | None) -> dict:
    """Observed provider-readiness facts only; never certify model parity or authorize a pick."""
    fixtures = (intake or {}).get("fixtures")
    scored = (shadow or {}).get("scored")
    rows = fixtures if isinstance(fixtures, list) else []
    research = scored if isinstance(scored, list) else []
    def count_true(key: str) -> int:
        return sum(row.get(key) is True for row in rows if isinstance(row, dict))
    def scored_true(key: str) -> int:
        return sum(row.get(key) is True for row in research if isinstance(row, dict))
    return {
        "source_fixture_rows_observed": len(rows) if isinstance(fixtures, list) else None,
        "research_scored_rows_observed": len(research) if isinstance(scored, list) else None,
        "provider_crosswalk_verified_rows": count_true("provider_identity_crosswalk_verified"),
        "browser_identity_verified_rows": count_true("browser_identity_verified"),
        "historical_features_verified_rows": count_true("historical_features_verified"),
        "research_source_parity_verified_rows": scored_true("calibrated_source_parity_verified"),
        "verified_execution_quotes": (quote or {}).get("bookmaker_quote_verified_count"),
        "provider_entitlement_expired_after_bogota_date": "2026-10-28",
        "research_probability_not_production_p_matrix": True,
        "provider_replacement_certified": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def _independent_status(root: Path, day: str) -> dict:
    folder = root / "evidence/football_world_inventory" / day
    intake = _read_json(folder / "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json")
    sofa = _read_json(folder / "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json")
    flash = _read_json(folder / "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json")
    shadow = _read_json(folder / "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json")
    quote = _read_json(folder / "MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json")
    tennis_folder = root / "evidence/tennis_calendar_reconciliation" / day
    tennis = _read_json(tennis_folder / "MATRIX_TENNIS_OPERA_02NOV_PHYSICAL_HANDOFF.json")
    tennis_review = _read_json(tennis_folder / "MATRIX_TENNIS_OPERA_DUAL_SOURCE_LINK_REVIEW.json")
    # These sources are only observed browser links. They are NOT the canonical
    # daily_prematch_reports or authorized Telegram inputs. Never count them as such.
    browser_sofa = _read_json(folder / "MATRIX_SOFASCORE_OPERA_VISIBLE_LINKS.json")
    browser_flash = _read_json(folder / "MATRIX_FLASHSCORE_OPERA_VISIBLE_LINKS.json")
    browser_pairs = _read_json(folder / "MATRIX_OPERA_TWO_SOURCE_LINK_RECONCILIATION.json")
    def observed_count(payload: dict | None, source: str) -> int | None:
        if not isinstance(payload, dict) or payload.get("source") != source:
            return None
        if payload.get("target_date_bogota") != day:
            return None
        governance = payload.get("governance") or {}
        if governance.get("real_money") != "BLOCKED" or governance.get("telegram_signal_authorized") is not False:
            return None
        rows = payload.get("observations")
        count = payload.get("distinct_observed_match_urls")
        if not isinstance(rows, list) or not isinstance(count, int) or len(rows) != count:
            return None
        return count
    sofa_links = observed_count(browser_sofa, "SOFASCORE")
    flash_links = observed_count(browser_flash, "FLASHSCORE")
    pair_count = None
    if (sofa_links is not None and flash_links is not None and
        isinstance(browser_pairs, dict) and
        browser_pairs.get("target_date_bogota") == day and
        browser_pairs.get("telegram_signals_authorized") is False and
        browser_pairs.get("real_money") == "BLOCKED"):
        n = browser_pairs.get("one_to_one_link_identity_candidate_count")
        rows = browser_pairs.get("one_to_one_link_identity_candidates")
        if isinstance(n, int) and isinstance(rows, list) and n == len(rows):
            pair_count = n
    observed = {"intake": intake is not None, "sofascore": sofa is not None,
                "flashscore": flash is not None, "shadow": shadow is not None,
                "quote": quote is not None, "tennis_browser_handoff": tennis is not None,
                "tennis_browser_link_review": tennis_review is not None,
                "football_sofascore_observed_links": sofa_links is not None,
                "football_flashscore_observed_links": flash_links is not None,
                "football_browser_link_pair_review": pair_count is not None}
    return {
        "source_files_parsed": observed,
        "independent_gate_detail": _independent_gate_detail(intake, shadow, quote),
        "independent_football_fixtures": intake.get("fixture_count") if intake else None,
        "sofascore_fixture_matches": sofa.get("matched_count") if sofa else None,
        "flashscore_fixture_matches": flash.get("matched_count") if flash else None,
        "research_scored_count": shadow.get("scored_count") if shadow else None,
        "exact_bookmaker_quotes_verified": quote.get("bookmaker_quote_verified_count") if quote else None,
        "quote_quota_status": quote.get("quota_status") if quote else None,
        "historical_feature_equivalence_verified": bool(intake and intake.get("governed_feature_equivalence_verified") is True and shadow and shadow.get("historical_source_equivalence_verified") is True),
        "independent_source_promotes_telegram": False,
        "tennis_browser_handoff_present": tennis is not None or tennis_review is not None,
        "tennis_browser_link_candidates": (
            tennis_review.get("candidate_pair_count")
            if tennis_review and tennis_review.get("target_date_bogota") == day
            and tennis_review.get("signal_generation_authorized") is False else None
        ),
        "tennis_kickoff_and_surface_verified": bool(tennis and tennis.get("utc_kickoff_verified") is True and tennis.get("surface_verified") is True),
        "football_browser_links_observed_only": {
            "sofascore": sofa_links, "flashscore": flash_links,
            "one_to_one_slug_candidates_not_certified_fixtures": pair_count,
        },
        "upstream_recovery_state": (
            "BROWSER_LINKS_OBSERVED_WAITING_INDEPENDENT_PROVIDER_AND_CANONICAL_MODEL"
            if sofa_links is not None and flash_links is not None and intake is None
            else "INDEPENDENT_PROVIDER_PRESENT_CANONICAL_EQUIVALENCE_NOT_CERTIFIED"
            if intake is not None and intake.get("governed_feature_equivalence_verified") is not True
            else "INSUFFICIENT_BROWSER_AND_PROVIDER_EVIDENCE"
        ),
        "diagnostic_only": True,
    }


def inspect(root: Path, today: str, tomorrow: str) -> dict:
    dates = (today, tomorrow)
    football_patterns = ("browser_physical_verification/*.json", "shadow_quote_freeze/*.json", "over25_shadow_ev/*.json")
    football = {day: {pattern: len(list((root / "evidence/api_football/daily_prematch_reports" / day).glob(pattern))) for pattern in football_patterns} for day in dates}
    tennis = {day: len(list((root / "evidence/tennis_signals" / day).glob("*.json"))) for day in dates}
    total = sum(sum(counts.values()) for counts in football.values()) + sum(tennis.values())
    return {
        "schema": "MATRIX_TELEGRAM_CANONICAL_INPUT_HEALTH_V2",
        "dates_bogota": list(dates),
        "football_files": football,
        "tennis_files": tennis,
        "total_canonical_files": total,
        "independent_discovery_diagnostic_only": {day: _independent_status(root, day) for day in dates},
        "independent_evidence_never_counts_as_canonical": True,
        "signal_emission_authorized_by_this_check": False,
        "status": "INPUTS_PRESENT_NOT_SIGNAL_CERTIFIED" if total else "FAIL_CLOSED_NO_CANONICAL_INPUTS",
        "provider_calls": 0,
        "telegram_messages_sent": 0,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }


def main() -> int:
    now = datetime.now(ZoneInfo("America/Bogota")).date()
    result = inspect(Path("."), now.isoformat(), (now + timedelta(days=1)).isoformat())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["total_canonical_files"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
