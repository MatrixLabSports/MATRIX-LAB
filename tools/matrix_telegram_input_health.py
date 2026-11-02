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


def _independent_status(root: Path, day: str) -> dict:
    folder = root / "evidence/football_world_inventory" / day
    intake = _read_json(folder / "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json")
    sofa = _read_json(folder / "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json")
    flash = _read_json(folder / "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json")
    shadow = _read_json(folder / "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json")
    quote = _read_json(folder / "MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json")
    tennis = _read_json(root / "evidence/tennis_calendar_reconciliation" / day /
                        "MATRIX_TENNIS_OPERA_02NOV_PHYSICAL_HANDOFF.json")
    observed = {"intake": intake is not None, "sofascore": sofa is not None,
                "flashscore": flash is not None, "shadow": shadow is not None,
                "quote": quote is not None, "tennis_browser_handoff": tennis is not None}
    return {
        "source_files_parsed": observed,
        "independent_football_fixtures": intake.get("fixture_count") if intake else None,
        "sofascore_fixture_matches": sofa.get("matched_count") if sofa else None,
        "flashscore_fixture_matches": flash.get("matched_count") if flash else None,
        "research_scored_count": shadow.get("scored_count") if shadow else None,
        "exact_bookmaker_quotes_verified": quote.get("bookmaker_quote_verified_count") if quote else None,
        "quote_quota_status": quote.get("quota_status") if quote else None,
        "historical_feature_equivalence_verified": bool(intake and intake.get("governed_feature_equivalence_verified") is True and shadow and shadow.get("historical_source_equivalence_verified") is True),
        "independent_source_promotes_telegram": False,
        "tennis_browser_handoff_present": tennis is not None,
        "tennis_kickoff_and_surface_verified": bool(tennis and tennis.get("utc_kickoff_verified") is True and tennis.get("surface_verified") is True),
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
