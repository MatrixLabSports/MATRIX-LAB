"""Read-only, source-bound three-provider calendar identity certificate.

This certifies only pre-existing fixture/time identity assertions. It NEVER maps
football-data.org fixture IDs to API-Football IDs, generates p_matrix, quotes,
canonical model features, or Telegram signals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
NAMES = {
    "source": "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
    "sofascore": "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
    "flashscore": "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",
}

def load_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("SOURCE_JSON_ROOT_NOT_OBJECT")
    return obj

def unique_map(rows: list, key: str) -> dict:
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("SOURCE_INVALID_ROW")
        value = str(row.get(key) or "").strip()
        if not value or value in result:
            raise ValueError("SOURCE_MISSING_OR_DUPLICATE_ID:" + key)
        result[value] = row
    return result

def aware_kickoff(token: str, target_day: str) -> str:
    d = datetime.fromisoformat(str(token).replace("Z", "+00:00"))
    if d.tzinfo is None or d.astimezone(BOGOTA).date().isoformat() != target_day:
        raise ValueError("SOURCE_KICKOFF_NOT_TARGET_BOGOTA_DATE")
    return d.isoformat()

def certify(folder: Path, target_day: str) -> dict:
    datetime.strptime(target_day, "%Y-%m-%d")
    paths = {name: folder / filename for name, filename in NAMES.items()}
    files = {name: load_json(path) for name, path in paths.items()}
    source, sofa, flash = files["source"], files["sofascore"], files["flashscore"]
    for item in (source, sofa, flash):
        if item.get("signal_generation_authorized") is not False:
            raise ValueError("SOURCE_SIGNALS_NOT_EXPLICITLY_BLOCKED")
        if item.get("real_money") != "BLOCKED":
            raise ValueError("SOURCE_REAL_MONEY_GUARD_INVALID")
    if sofa.get("target_date_bogota") != target_day or flash.get("target_date_bogota") != target_day:
        raise ValueError("CROSSCHECK_DATE_MISMATCH")
    fixtures = source.get("fixtures")
    smatched, fmatched = sofa.get("matched"), flash.get("matched")
    if not all(isinstance(x, list) for x in (fixtures, smatched, fmatched)):
        raise ValueError("SOURCE_ROWS_MISSING")
    if source.get("fixture_count") != len(fixtures) or sofa.get("matched_count") != len(smatched) or flash.get("matched_count") != len(fmatched):
        raise ValueError("SOURCE_COUNT_MISMATCH")
    src = unique_map(fixtures, "source_fixture_id")
    sofas = unique_map(smatched, "fixture_id")
    flashes = unique_map(fmatched, "source_fixture_id")
    certified = []
    used_sofa_ids = set()
    used_flash_ids = set()
    for fixture_id, f in sorted(flashes.items()):
        a, b = src.get(fixture_id), sofas.get(fixture_id)
        if a is None or b is None:
            raise ValueError("TRIPLE_SOURCE_IDENTITY_MISSING:" + fixture_id)
        if f.get("three_source_calendar_identity_verified") is not True or b.get("identity_time_and_teams_verified") is not True:
            raise ValueError("CALENDAR_IDENTITY_NOT_VERIFIED:" + fixture_id)
        if a.get("source") != "FOOTBALL_DATA_ORG" or a.get("api_football_fixture_id") is not None:
            raise ValueError("SOURCE_ID_NAMESPACE_MISMATCH:" + fixture_id)
        if a.get("signal_generation_authorized") is not False:
            raise ValueError("SOURCE_FIXTURE_SIGNAL_NOT_BLOCKED:" + fixture_id)
        kickoff = aware_kickoff(a.get("kickoff_utc"), target_day)
        if kickoff != aware_kickoff(b.get("kickoff_utc"), target_day) or kickoff != aware_kickoff(f.get("kickoff_utc"), target_day):
            raise ValueError("TRIPLE_SOURCE_KICKOFF_MISMATCH:" + fixture_id)
        sof_id = str(b.get("sofascore_event_id") or "")
        flash_id = str(f.get("flashscore_mid") or "")
        if not sof_id or sof_id != str(f.get("sofascore_event_id") or "") or not flash_id:
            raise ValueError("THIRD_PARTY_EVENT_IDENTITY_MISMATCH:" + fixture_id)
        if sof_id in used_sofa_ids or flash_id in used_flash_ids:
            raise ValueError("NON_UNIQUE_EXTERNAL_EVENT_ID")
        used_sofa_ids.add(sof_id)
        used_flash_ids.add(flash_id)
        certified.append({
            "independent_fixture_id": fixture_id,
            "independent_source": "FOOTBALL_DATA_ORG",
            "sofascore_event_id": sof_id,
            "flashscore_mid": flash_id,
            "kickoff_utc": kickoff,
            "home": a.get("home"),
            "away": a.get("away"),
            "sofascore_url": b.get("sofascore_url"),
            "flashscore_url": f.get("flashscore_url"),
            "calendar_identity_verified": True,
            "api_football_crosswalk_certified": False,
            "historical_feature_parity_verified": False,
            "production_probability_authorized": False,
            "quote_verified": False,
            "telegram_signal_authorized": False,
        })
    return {
        "schema": "MATRIX_INDEPENDENT_TRIPLE_SOURCE_CALENDAR_CERT_V1",
        "target_date_bogota": target_day,
        "status": "CALENDAR_IDENTITY_ONLY_NOT_MODEL_EQUIVALENCE",
        "independent_fixture_total": len(src),
        "triple_source_calendar_identities": len(certified),
        "not_triple_source_confirmed": len(src) - len(certified),
        "rows": certified,
        "sources_sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in paths.items()},
        "source_priority": ["SofaScore", "Flashscore", "football-data.org"],
        "api_football_fixture_id_mapping_present": False,
        "model_feature_equivalence_verified": False,
        "canonical_model_input_authorized": False,
        "telegram_signal_authorized": False,
        "no_derived_p_matrix": True,
        "no_post_kickoff_backfill": True,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--day", required=True)
    p.add_argument("--root", default=".")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    root = Path(args.root)
    folder = root / "evidence" / "football_world_inventory" / args.day
    certificate = certify(folder, args.day)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(certificate, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": certificate["status"], "identities": certificate["triple_source_calendar_identities"], "model_authorized": False, "signals": False}, sort_keys=True))

if __name__ == "__main__":
    main()
