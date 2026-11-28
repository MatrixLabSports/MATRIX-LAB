"""Choose a physically certified independent Over2.5 prematch day, across Bogota midnight.

Selection is read-only. It never promotes probabilities, bypasses quotas,
produces execution rows or sends Telegram.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
WINDOW_SECONDS = 120 * 60
ALLOWED_SOURCE_ORDER = ["SOFASCORE", "FLASHSCORE", "APIS"]
ARTIFACTS = (
    "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
    "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json",
    "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
    "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",
)

def parse_utc(value: object) -> datetime:
    value = str(value or "")
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return moment.astimezone(timezone.utc)

def choose(root: Path, *, now: datetime) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("NOW_REQUIRES_TIMEZONE")
    clock = now.astimezone(timezone.utc)
    local_day = clock.astimezone(BOGOTA).date()
    result = {
        "schema": "MATRIX_INDEPENDENT_OVER25_DAY_SELECTOR_V1",
        "checked_at_utc": clock.isoformat(),
        "today_bogota": local_day.isoformat(),
        "status": "NO_CERTIFIED_PREMATCH_FIXTURES_IN_120M_WINDOW",
        "selected_date": None,
        "selected_fixture_id": None,
        "seconds_until_kickoff": None,
        "blocked_dates": [],
        "source_order": ALLOWED_SOURCE_ORDER,
        "telegram_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    candidates = []
    for day in (local_day, local_day + timedelta(days=1)):
        date_str = day.isoformat()
        folder = root / date_str
        if any(not (folder / a).is_file() for a in ARTIFACTS):
            result["blocked_dates"].append({"date": date_str, "reason": "SOURCE_ARTIFACT_MISSING"})
            continue
        try:
            intake, shadow, browser, flash = (
                json.loads((folder / name).read_text(encoding="utf-8")) for name in ARTIFACTS
            )
            if not all(isinstance(x, dict) for x in (intake, shadow, browser, flash)):
                raise ValueError("NOT_A_DICTIONARY")
            if {intake.get("target_date_bogota"), shadow.get("target_date_bogota"),
                browser.get("target_date_bogota"), flash.get("target_date_bogota")} != {date_str}:
                raise ValueError("MISMATCHED_SOURCE_DATES")
            if intake.get("schema") != "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1":
                raise ValueError("INVALID_INTAKE_SCHEMA")
            if shadow.get("schema") != "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1":
                raise ValueError("INVALID_SHADOW_SCHEMA")
            if browser.get("schema") != "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK_V1":
                raise ValueError("INVALID_BROWSER_SCHEMA")
            if flash.get("schema") != "MATRIX_FLASH_FOOTBALL_CROSSCHECK_V1":
                raise ValueError("INVALID_FLASH_SCHEMA")
            if (intake.get("source_order") != ALLOWED_SOURCE_ORDER or
                browser.get("source_order") != ALLOWED_SOURCE_ORDER or
                flash.get("source_order") != ALLOWED_SOURCE_ORDER):
                raise ValueError("BROWSER_FIRST_SOURCE_ORDER_INVALID")
            if intake.get("real_money") != "BLOCKED" or shadow.get("real_money") != "BLOCKED" or browser.get("real_money") != "BLOCKED" or flash.get("real_money") != "BLOCKED":
                raise ValueError("REAL_MONEY_NOT_BLOCKED")
            if any((intake.get("signal_generation_authorized") is not False,
                    shadow.get("market_signal_authorized") is not False,
                    browser.get("signal_generation_authorized") is not False,
                    flash.get("signal_generation_authorized") is not False,
                    shadow.get("parameter_refit") is not False,
                    shadow.get("odds_used_to_generate_probability") is not False)):
                raise ValueError("GOVERNANCE_AUTHORIZATION_INVALID")
            if browser.get("status") != "PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL":
                raise ValueError("PRIMARY_BROWSER_CROSSCHECK_NOT_PASSED")
            if browser.get("rejected_count") != 0:
                raise ValueError("PRIMARY_BROWSER_CROSSCHECK_HAS_REJECTIONS")
            if (flash.get("status") != "PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS"
                or flash.get("flashscore_verified") is not True or flash.get("rejected_count") != 0):
                raise ValueError("FLASH_BROWSER_CROSSCHECK_NOT_PASSED")
            checked = {str(item["fixture_id"]): str(item["kickoff_utc"])
                       for item in browser.get("matched", []) if isinstance(item, dict)}
            if len(checked) != browser.get("matched_count") or len(checked) != len(browser.get("matched", [])):
                raise ValueError("DUPLICATE_OR_INVALID_BROWSER_MATCHES")
            double_checked = {str(item["source_fixture_id"]): str(item["kickoff_utc"])
                              for item in flash.get("matched", []) if isinstance(item, dict)}
            if len(double_checked) != flash.get("matched_count") or len(double_checked) != len(flash.get("matched", [])):
                raise ValueError("DUPLICATE_OR_INVALID_FLASH_MATCHES")
            scored = {str(item["source_fixture_id"]): str(item["kickoff_utc"])
                      for item in shadow.get("scored", []) if isinstance(item, dict)}
            if len(scored) != len(shadow.get("scored", [])):
                raise ValueError("DUPLICATE_SCORED_FIXTURE_ID")
            for f in intake.get("fixtures", []):
                if not isinstance(f, dict):
                    continue
                fid = str(f.get("source_fixture_id") or "")
                start = str(f.get("kickoff_utc") or "")
                if checked.get(fid) != start or double_checked.get(fid) != start or scored.get(fid) != start:
                    continue
                kickoff = parse_utc(start)
                seconds = (kickoff - clock).total_seconds()
                if 0 < seconds <= WINDOW_SECONDS and kickoff.astimezone(BOGOTA).date() == day:
                    candidates.append((kickoff, date_str, fid))
        except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
            result["blocked_dates"].append({"date":date_str,"reason":type(exc).__name__ + "_INVALID_ARTIFACT"})
    if candidates:
        kickoff, selected, fid = min(candidates)
        result["status"] = "CERTIFIED_SOURCE_PREMATCH_DAY_SELECTED_QUOTES_STILL_UNVERIFIED"
        result["selected_date"] = selected
        result["selected_fixture_id"] = fid
        result["seconds_until_kickoff"] = int((kickoff - clock).total_seconds())
    return result

def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path("evidence/football_world_inventory"))
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    response=choose(a.root,now=datetime.now(timezone.utc))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(response,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(response,sort_keys=True))
if __name__=="__main__":
    main()
