"""Reconcile immutable browser/provider research receipts, never authorize models.

This checks the recorded provenance, not the underlying browser response bytes.
Browser time-zone and original-model enriched PIT remain separate missing gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

SCHEMA = "MATRIX_THREE_SOURCE_RESEARCH_RECEIPT_GATE_V1"
ORIG = "MATRIX_FOOTBALL_BROWSER_FIRST_PROSPECTIVE_RESEARCH_RECEIPT_V1"
LATER = "MATRIX_FLASH_EXACT_MID_PREMATCH_RESEARCH_V1"
PROOF = "MATRIX_FREE_API_INDEPENDENT_PROBE_V2"
ORDER = ["SOFASCORE", "FLASHSCORE", "FOOTBALL_DATA_ORG"]


def utc(value: str) -> datetime:
    v = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if v.utcoffset() is None:
        raise ValueError("UTC_TIMESTAMP_WITH_TIMEZONE_REQUIRED")
    return v.astimezone(timezone.utc)


def require(test: bool, code: str):
    if not test:
        raise ValueError(code)


def reject_promotion(obj: dict, keys: list[str]):
    for key in keys:
        require(obj.get(key) is False, "UNAUTHORIZED_PROMOTION_OR_UNTRUSTED_GOVERNANCE:" + key)


def verify(old: dict, new: dict, proof: dict) -> dict:
    require(old.get("schema") == ORIG and new.get("schema") == LATER and proof.get("schema") == PROOF, "SCHEMA_MISMATCH")
    require(old.get("source_order") == ORDER and new.get("source_order") == ORDER, "SOURCE_ORDER_MISMATCH")
    reject_promotion(old["governance"], ["canonical_model_input_authorized", "production_p_matrix_authorized", "telegram_signal_authorized", "automatic_wagering", "three_source_canonical_crosswalk_certified", "original_enriched_pit_equivalence_certified"])
    reject_promotion(new["admission"], ["canonical_enriched_model_input_authorized", "production_p_matrix_authorized", "telegram_signal_authorized", "automatic_wagering", "original_six_league_pit_equivalence_certified", "full_three_source_independent_event_identity_certified", "original_enriched_pit_features_certified"] if "original_enriched_pit_features_certified" in new["admission"] else ["canonical_enriched_model_input_authorized", "production_p_matrix_authorized", "telegram_signal_authorized", "automatic_wagering", "original_six_league_pit_equivalence_certified", "full_three_source_independent_event_identity_certified"])
    require(old["governance"].get("real_money") == new["admission"].get("real_money") == "BLOCKED", "REAL_MONEY_NOT_BLOCKED")
    o, n = old["event"], new["match"]
    require(old.get("target_bogota_date") == new.get("target_date_bogota"), "EVENT_TARGET_DAY_MISMATCH")
    require((o["home"], o["away"]) == (n["home"], n["away"]), "EVENT_TEAM_MISMATCH")
    require(str(o["sofascore"]["observed_event_id"]) == str(n["sofascore_event_id"]), "SOFASCORE_ID_MISMATCH")
    require(o["sofascore"]["observed_event_url"] == n["sofascore_url"], "SOFASCORE_URL_MISMATCH")
    require(o["flashscore"]["observed_event_url"].rstrip("/") == n["flashscore_mid_bearing_url"].split("?", 1)[0].rstrip("/"), "FLASHSCORE_EVENT_URL_MISMATCH")
    u = urlsplit(n["flashscore_mid_bearing_url"])
    mid = str(n["flashscore_mid"])
    require(u.scheme == "https" and u.hostname == "www.flashscore.co" and u.path.startswith("/partido/futbol/"), "FLASHSCORE_UNTRUSTED_ORIGIN")
    require(bool(re.fullmatch(r"[A-Za-z0-9]{8}", mid)), "FLASHSCORE_MID_FORMAT_INVALID")
    require(parse_qs(u.query).get("mid") == [mid], "FLASHSCORE_MID_LINK_MISMATCH")
    require(mid not in ("2Nmg27Er", "GIXvWgt9", "QJFTcmK7"), "KNOWN_HISTORIC_H2H_MID")
    require(str(o["source_provider_fixture_id"]) == str(n["football_data_org_fixture_id"]), "THIRD_SOURCE_FIXTURE_ID_MISMATCH")
    kickoff = utc(o["source_kickoff_utc"])
    require(kickoff == utc(n["football_data_org_kickoff_utc"]) == utc(o["football_data_org"]["kickoff_utc"]), "PROVIDER_KICKOFF_MISMATCH")
    require(utc(old["captured_at_utc"]) < kickoff, "OLD_RESEARCH_AFTER_KICKOFF")
    require(n["browser_clock_timezone_independently_attested"] is False and n["original_api_football_fixture_crosswalk_certified"] is False, "OVERSTATED_CERTIFICATION")
    target = old["target_bogota_date"]
    require(kickoff.astimezone(ZoneInfo("America/Bogota")).date().isoformat() == target, "EVENT_BOGOTA_DATE_MISMATCH")
    expected_local = kickoff.astimezone(ZoneInfo("America/Bogota")).strftime("%d.%m.%Y %H:%M")
    require(n["flashscore_current_page_display"] == expected_local and n["displayed_clock_consistent_with_bogota_utc_minus_5"] is True, "BROWSER_DISPLAY_NOT_CLAIMED")
    week = proof["football_named_competition_week_proof"]
    require(week.get("verified") is True and week.get("response", {}).get("http_status") == 200, "THIRD_SOURCE_RESPONSE_NOT_VERIFIED")
    rows = [x for x in week["source_fixtures_research_only"] if str(x.get("provider_fixture_id")) == str(n["football_data_org_fixture_id"])]
    require(len(rows) == 1, "THIRD_SOURCE_FIXTURE_MISSING_OR_DUPLICATE")
    item = rows[0]
    require(utc(item["kickoff_utc"]) == kickoff and item["home"] == o["football_data_org"]["home"] and item["away"] == o["football_data_org"]["away"], "THIRD_SOURCE_TEAM_OR_TIME_MISMATCH")
    require(str(week["response"]["response_sha256"]) == o["football_data_org"]["provider_response_sha256"], "THIRD_SOURCE_RESPONSE_HASH_MISMATCH")
    require(week["model_admission_authorized"] is False and week["historic_provider_id_equivalence_certified"] is False, "THIRD_SOURCE_PROMOTION_MISMATCH")
    return {
        "schema": SCHEMA,
        "status": "RESEARCH_RECEIPT_LINK_CONSISTENT_NO_PIT_OR_CANONICAL_CERTIFICATION",
        "target_date_bogota": target,
        "match": {"home": n["home"], "away": n["away"], "sofascore_event_id": str(n["sofascore_event_id"]), "flashscore_mid": mid, "football_data_org_fixture_id": str(n["football_data_org_fixture_id"]), "kickoff_utc": kickoff.isoformat()},
        "receipt_link_check_passed": True,
        "flashscore_mid_link_matches_current_event_receipt": True,
        "provider_response_bytes_rechecked_in_this_run": False,
        "browser_time_zone_independently_attested": False,
        "source_capture_time_for_new_browser_receipt_attested": False,
        "three_source_canonical_identity_certified": False,
        "original_api_football_fixture_crosswalk_certified": False,
        "original_enriched_pit_certified": False,
        "p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def run(old_path: Path, new_path: Path, proof_path: Path) -> dict:
    paths = {"earlier_browser_receipt": old_path, "new_browser_receipt": new_path, "prior_authenticated_provider_probe": proof_path}
    sources = {name: p.read_bytes() for name, p in paths.items()}
    result = verify(*(json.loads(sources[name]) for name in paths))
    result["read_source_sha256"] = {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()}
    result["read_source_paths"] = {name: str(path) for name, path in paths.items()}
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--earlier", type=Path, required=True)
    p.add_argument("--new", type=Path, required=True)
    p.add_argument("--provider", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    report = run(args.earlier, args.new, args.provider)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "production_authorized": report["p_matrix_authorized"]}, sort_keys=True))

if __name__ == "__main__":
    main()
