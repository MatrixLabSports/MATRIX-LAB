"""PIT browser-first preflight: record a hash-bound blocker instead of a failed shell step.

This is NOT a probability validator. Strict original attestation is called only
when the authentic calendar sources have at least one corroborated ELC event.
No network, quota, Telegram, model modification or synthetic predictions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

FILES = {
    "intake": "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
    "shadow": "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json",
    "sofa": "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
    "flash": "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",
}
SCHEMA = "MATRIX_INDEPENDENT_PIT_BROWSER_PREFLIGHT_V1"


def assess(root: Path, day: str, *, now: datetime) -> dict:
    date.fromisoformat(day)
    if now.utcoffset() is None:
        raise ValueError("PIT_PREFLIGHT_NEEDS_AWARE_CLOCK")
    folder = root / "evidence" / "football_world_inventory" / day
    docs, hashes, missing = {}, {}, []
    for key, name in FILES.items():
        path = folder / name
        if not path.is_file():
            missing.append(key)
            continue
        raw = path.read_bytes()
        if len(raw) > 24_000_000:
            raise ValueError("PIT_PREFLIGHT_SOURCE_TOO_LARGE")
        hashes[key] = hashlib.sha256(raw).hexdigest()
        docs[key] = json.loads(raw)
    intake = docs.get("intake") or {}
    shadow = docs.get("shadow") or {}
    sofa = docs.get("sofa") or {}
    flash = docs.get("flash") or {}
    fixtures = intake.get("fixtures") or []
    if not isinstance(fixtures, list):
        raise ValueError("PIT_PREFLIGHT_FIXTURES_MUST_BE_ARRAY")
    elc = {
        str(row["source_fixture_id"]) for row in fixtures if isinstance(row, dict)
        and row.get("source_competition_code") == "ELC"
        and str(row.get("source_competition_id")) == "2016"
        and row.get("source_fixture_id")
    }
    sofa_ids = {
        str(row.get("fixture_id")) for row in sofa.get("matched") or [] if isinstance(row, dict)
        and row.get("identity_time_and_teams_verified") is True
    }
    flash_ids = {
        str(row.get("source_fixture_id")) for row in flash.get("matched") or []
        if isinstance(row, dict)
        and row.get("three_source_calendar_identity_verified") is True
    }
    valid_sources = (
        not missing
        and intake.get("schema") == "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        and shadow.get("schema") == "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1"
        and sofa.get("schema") == "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK_V1"
        and flash.get("schema") == "MATRIX_FLASH_FOOTBALL_CROSSCHECK_V1"
        and all(doc.get("real_money") == "BLOCKED" for doc in docs.values())
        and all(doc.get("target_date_bogota") == day for doc in docs.values())
        and intake.get("source") == "FOOTBALL_DATA_ORG"
        and intake.get("provider_status") == "AUTHENTICATED_FIXTURE_CAPTURE"
        and intake.get("signal_generation_authorized") is False
        and shadow.get("market_signal_authorized") is False
        and shadow.get("parameter_refit") is False
        and sofa.get("signal_generation_authorized") is False
        and flash.get("signal_generation_authorized") is False
        and sofa.get("status") == "PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL"
        and flash.get("status") == "PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS"
        and flash.get("sofascore_verified") is True
        and flash.get("flashscore_verified") is True
        and (sofa.get("rejected_count") or 0) == 0
        and (flash.get("rejected_count") or 0) == 0
    )
    triple = sorted(elc & sofa_ids & flash_ids) if valid_sources else []
    if missing:
        reason = "BLOCKED_MISSING_SOURCE_DOCUMENTS"
    elif not elc:
        reason = "BLOCKED_NO_CHAMPIONSHIP_FIXTURES"
    elif not valid_sources:
        reason = "BLOCKED_TRIPLE_BROWSER_CALENDAR_EVIDENCE"
    elif not triple:
        reason = "BLOCKED_NO_EXACT_TRIPLE_SOURCE_CHAMPIONSHIP_MATCH"
    else:
        reason = "READY_STRICT_PIT_ATTESTATION_ONLY"
    return {
        "schema": SCHEMA, "target_date_bogota": day,
        "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "status": reason, "ready_for_strict_attestation": bool(triple),
        "source_sha256": hashes, "missing_sources": missing,
        "independent_fixture_count": len(fixtures),
        "independent_research_scored_count": len(shadow.get("scored") or []),
        "championship_native_fixtures": len(elc),
        "sofascore_verified_ids": len(sofa_ids),
        "flashscore_verified_ids": len(flash_ids),
        "exact_triple_source_championship_ids": triple,
        "no_model_parity_promotion": True,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False, "real_money": "BLOCKED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if any(x in args.out.parts for x in ("telegram", "daily_prematch_reports",
                                         "tennis_signals", "governance")):
        raise SystemExit("PIT_PREFLIGHT_CANNOT_WRITE_PRODUCTION")
    result = assess(args.root, args.date, now=datetime.now(timezone.utc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
                        + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "ready": result["ready_for_strict_attestation"],
                      "championship": result["championship_native_fixtures"],
                      "research_scores": result["independent_research_scored_count"],
                      "telegram_signal_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()
