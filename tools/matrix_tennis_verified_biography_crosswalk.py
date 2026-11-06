"""Independent research-only native-ID / pre-cut authority biography reconciliation.

Read only immutable, user-authorized browser captures and original pre-cut
identity authorities. Proves exact name + birthdate + IOC for a restricted
sample, NOT production feature equivalence or event-time synchronization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from tools.matrix_tennis_browser_challenger_pit_gate import (
    AUTHORITIES, COUNTRY_IOC, normal, timestamp,
)

DAYPATH = Path("evidence/tennis_calendar_physical")
REPORTPATH = Path("evidence/tennis_calendar_reconciliation")
MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
          "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "octubre": 10, "noviembre": 11,
          "diciembre": 12}
SPANISH_MONTHS = {name[:3]: n for name, n in MONTHS.items()}
SPANISH_MONTHS.update({"sep": 9, "set": 9})

def file(root: Path, path: Path):
    raw = (root / path).read_bytes()
    if len(raw) > 7_000_000:
        raise ValueError("INPUT_OVERSIZE")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()

def spanish_birthday(value: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2}) de ([a-záéíóú]+) de (\d{4})\s*", value)
    if not m or m.group(2) not in MONTHS:
        raise ValueError("VISIBLE_BIRTHDATE_INVALID")
    return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).strftime("%Y%m%d")

def quoted_upcoming(value: str):
    m = re.search(r"el (\d{1,2}) ([a-z]{3}) (\d{4}), (\d{2}:\d{2}:\d{2}) UTC contra (.+?) en ", value)
    if not m or m.group(2) not in SPANISH_MONTHS:
        return None
    d = date(int(m.group(3)), SPANISH_MONTHS[m.group(2)], int(m.group(1)))
    at = datetime.strptime(d.isoformat() + " " + m.group(4), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return at, m.group(5)

def verify(root: Path, target_day: str):
    day = date.fromisoformat(target_day)
    bio, biosha = file(root, DAYPATH/target_day/"MATRIX_TENNIS_OPERA_BIOGRAPHY_VISIBLE_OBSERVATIONS.json")
    details, detailsha = file(root, DAYPATH/target_day/"sofascore_verified_match_details.json")
    cross, crosssha = file(root, REPORTPATH/target_day/"MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json")
    flash, flashsha = file(root, DAYPATH/target_day/"MATRIX_TENNIS_FLASHSCORE_MATCH_TIME_VISIBLE_OBSERVATIONS.json")
    if (bio.get("schema") != "MATRIX_TENNIS_OPERA_BIOGRAPHY_VISIBLE_OBSERVATIONS_V1"
        or details.get("schema") != "MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1"
        or cross.get("schema") != "MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_V1"
        or flash.get("schema") != "MATRIX_TENNIS_FLASHSCORE_VISIBLE_MATCH_CLOCK_V1"
        or len({bio.get("target_date_bogota"), details.get("target_date_bogota"),
                cross.get("target_date_bogota"), flash.get("target_date_bogota"), target_day}) != 1
        or any(x.get("real_money") != "BLOCKED" for x in (bio, details, cross))
        or bio.get("paid_api_used") is not False
        or details.get("telegram_signal_authorized") is not False
        or bio.get("official_holdout_admitted") != 0
        or flash.get("official_holdout_admitted") != 0
        or flash.get("paid_api_used") is not False
        or flash.get("local_timezone_assertion_authorized") is not False
        or flash.get("real_money") != "BLOCKED"
        or cross.get("source_event_equivalence_certified") is not False):
        raise ValueError("SOURCE_GOVERNANCE_OR_DATE_MISMATCH")
    captured = timestamp(bio["captured_at_utc"])
    flash_at = timestamp(flash["observed_at_utc"])
    detailed = timestamp(details["observed_at_utc"])
    if captured < detailed:
        raise ValueError("BIOGRAPHY_CAPTURE_BEFORE_DETAIL_SNAPSHOT_UNCONFIRMED")
    flashrows = {}
    for row in flash.get("rows") or []:
        sid = str(row.get("sofascore_id") or "")
        if sid in flashrows or row.get("visible_text_role") != "staticText":
            raise ValueError("DUPLICATE_OR_UNTRUSTED_FLASHSCORE_CLOCK")
        value = str(row.get("visible_match_datetime_text") or "")
        try:
            rawclock = datetime.strptime(value, "%d.%m.%Y %H:%M")
        except ValueError as exc:
            raise ValueError("FLASHSCORE_CLOCK_MALFORMED") from exc
        if rawclock.date() != day:
            raise ValueError("FLASHSCORE_CLOCK_WRONG_TARGET_DAY")
        flashrows[sid] = (row, rawclock)
    if len(flashrows) != len(details.get("events") or []):
        raise ValueError("FLASHSCORE_CLOCK_ROWS_MISSING_OR_EXTRA")
    profiles = bio.get("profiles")
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 30:
        raise ValueError("BIOGRAPHY_PROFILE_COUNT_INVALID")
    native = {}
    for p in profiles:
        pid = str(p.get("sofascore_player_id") or "")
        u = urlparse(str(p.get("url") or ""))
        if (not pid.isdigit() or u.hostname not in ("sofascore.com", "www.sofascore.com")
            or u.scheme != "https" or not u.path.startswith("/es/tennis/player/")
            or u.path.split("/")[-1] != pid or pid in native or
            p.get("birthdate_source_role") != "staticText"):
            raise ValueError("UNTRUSTED_OR_DUPLICATED_NATIVE_PROFILE")
        native[pid] = p
    authorities = {}
    authority_shas = {}
    for lane, name in AUTHORITIES.items():
        z, digest = file(root, Path(name))
        if (z.get("outcomes_used") is not False
            or z.get("post_cut_competitive_data_used") is not False
            or z.get("silent_imputation") is not False
            or z.get("real_money") != "BLOCKED"):
            raise ValueError("PRE_CUT_AUTHORITY_INVALID")
        authorities[lane] = z.get("records", [])
        authority_shas[lane] = digest
    crossrows = {str(x["sofascore_id"]): x for x in cross.get("matches", [])}
    people = []
    events = []
    provider_ids = set()
    for event in details.get("events") or []:
        sid = str(event.get("sofascore_event_id") or "")
        lane = event.get("surface")
        kickoff = timestamp(event["kickoff_utc"])
        if (lane not in AUTHORITIES or sid not in crossrows or
            kickoff.astimezone(timezone.utc) <= captured
            or detailed >= kickoff or
            event.get("sofascore_url") != crossrows[sid].get("sofascore_url")
            or event.get("flashscore_url") != crossrows[sid].get("flashscore_url")
            or len(event.get("players") or []) != 2):
            raise ValueError("NON_PROSPECTIVE_OR_UNTRUSTED_EVENT")
        if sid not in flashrows:
            raise ValueError("MISSING_INDEPENDENT_MATCH_PAGE_CLOCK")
        frow, fclock = flashrows[sid]
        if (frow.get("flashscore_url") != event["flashscore_url"]
            or str(frow.get("flashscore_mid")) != str(event.get("flashscore_mid"))
            or str(frow.get("source_name_token_key"))
                 != str(crossrows[sid].get("source_name_token_key"))
            or flash_at >= kickoff):
            raise ValueError("UNTRUSTED_OR_POSTMATCH_FLASHSCORE_CLOCK")
        expected_clock = datetime.strptime(
            str(event["local_visible_date"]) + " " + str(event["local_visible_time"]),
            "%d/%m/%Y %H:%M")
        clock_display_agrees = (expected_clock == fclock)
        event_people = []
        quote_conflicts = []
        for player in event["players"]:
            pid = str(player.get("sofascore_player_id") or "")
            if pid not in native:
                raise ValueError("PROFILE_NOT_CAPTURED_FOR_MATCH")
            record = native[pid]
            if (record["name"] != player.get("name")
                or record["url"] != player.get("profile_url")
                or record["country"] != player.get("country")):
                raise ValueError("NATIVE_PROFILE_IDENTITY_DISAGREEMENT")
            ioc = COUNTRY_IOC.get(record["country"])
            if not ioc:
                raise ValueError("NATIONALITY_UNKNOWN")
            birthday = spanish_birthday(record["birth_date_visible"])
            options = [x for x in authorities[lane]
                       if normal(x.get("provider_display_name")) == normal(record["name"])
                       and x.get("provider_ioc_canonical") == ioc
                       and any(b.get("dob") == birthday and b.get("ioc") == ioc
                               and normal(b.get("name")) == normal(record["name"])
                               for b in x.get("biographical_candidates") or [])]
            if len(options) != 1:
                raise ValueError("ORIGINAL_PROVIDER_PROFILE_BIOGRAPHY_NOT_UNIQUE")
            provider = options[0]
            provider_id = provider.get("provider_player_id")
            if not provider_id or provider_id in provider_ids:
                raise ValueError("ORIGINAL_PROVIDER_ID_REUSED_OR_MISSING")
            provider_ids.add(provider_id)
            history = provider.get("pre_cut_history") or {}
            if (int(history.get("rows") or 0) < 5
                or int(history.get("latest_row_date") or 99999999) >= int(day.strftime("%Y%m%d"))):
                raise ValueError("HISTORIC_PRE_CUT_WINDOW_INVALID")
            upcoming = quoted_upcoming(record.get("next_match_text_visible") or "")
            date_status = "NO_SAME_EVENT_PROFILE_START_TO_COMPARE"
            if upcoming and upcoming[0].date() == kickoff.date():
                other_names = [x["name"] for x in event["players"] if x["name"] != record["name"]]
                if len(other_names) == 1 and normal(upcoming[1]) == normal(other_names[0]):
                    if upcoming[0] != kickoff:
                        date_status = "SOURCE_PROFILE_VS_EVENT_KICKOFF_CONFLICT"
                        quote_conflicts.append({"player": record["name"],
                                                "event_kickoff_utc": kickoff.isoformat(),
                                                "profile_next_kickoff_utc": upcoming[0].isoformat()})
                    else:
                        date_status = "PROFILE_AND_EVENT_KICKOFF_MATCH"
            p = {"name":record["name"], "lane":lane,
                 "sofascore_native_player_id": pid,
                 "original_provider_player_id": provider_id,
                 "original_authority_sha256": authority_shas[lane],
                 "exact_name_birthdate_country_match": True,
                 "birthdate": birthday, "ioc": ioc,
                 "historical_pre_cut_rows": history["rows"],
                 "pre_cut_latest_row_date": history["latest_row_date"],
                 "profile_start_check": date_status,
                 "provider_native_id_mapped_research_only": True,
                 "production_feature_equivalence_certified": False}
            event_people.append(p)
            people.append(p)
        events.append({"sofascore_id": sid, "surface": lane,
                       "prematch_detail_sha256": detailsha,
                       "biographical_triplet_matches": len(event_people),
                       "schedule_conflicts": quote_conflicts,
                       "independent_match_page_clock": {
                           "sofascore_local_display": expected_clock.strftime("%d.%m.%Y %H:%M"),
                           "flashscore_local_display": fclock.strftime("%d.%m.%Y %H:%M"),
                           "displayed_clock_agrees": clock_display_agrees,
                           "flashscore_timezone_explicitly_attested": False,
                           "flashscore_visible_capture_sha256": flashsha,
                           "status": ("MATCH_PAGE_CLOCK_DISPLAY_CONCORDANT_WITHOUT_TZ_ATTESTATION"
                                      if clock_display_agrees else
                                      "TWO_PROVIDER_MATCH_PAGE_CLOCK_CONFLICT"),
                       },
                       "prospective_model_admission_authorized": False,
                       "historical_model_feature_pit_equivalence": False,
                       "status": ("TWO_PROVIDER_MATCH_PAGE_CLOCK_CONFLICT_FAIL_CLOSED"
                                  if not clock_display_agrees else
                                  "TWO_MATCH_PAGE_CLOCKS_AGREE_PROFILE_TEXT_STALE_MODEL_PIT_BLOCKED"
                                  if quote_conflicts else
                                  "BIOGRAPHICAL_IDENTITY_MATCH_ONLY_FEATURE_PIT_MISSING")})
    if len(people) != len(profiles):
        raise ValueError("UNCORRELATED_VISIBLE_PROFILE_ROW")
    return {"schema": "MATRIX_TENNIS_RESEARCH_BIOGRAPHY_CROSSWALK_LAST_V1",
            "target_date_bogota":target_day,
            "source_sha256": {"biography":biosha, "prematch_details":detailsha,
                              "source_crossmatch":crosssha, "flashscore_match_clock":flashsha,
                              "original_authorities":authority_shas},
            "biographical_id_triplets_matched":len(people),
            "total_source_metadata_events":len(events),
            "events_with_schedule_conflicts":sum(bool(e["schedule_conflicts"]) for e in events),
            "events_with_match_page_clock_conflicts":sum(not e["independent_match_page_clock"]["displayed_clock_agrees"] for e in events),
            "events_with_match_page_clock_display_agreement":sum(e["independent_match_page_clock"]["displayed_clock_agrees"] for e in events),
            "events":events,"players":people,
            "provider_id_equivalence_approved_for_model":False,
            "current_rank_and_pre_cut_feature_parity_certified":False,
            "new_hard_holdout_admissions":0,"new_clay_holdout_admissions":0,
            "telegram_signal_authorized":False,"real_money":"BLOCKED",
            "automatic_wagering":False,"paid_api_used":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--root",type=Path,default=Path.cwd())
    args=p.parse_args()
    result=verify(args.root,args.date)
    path=args.root/REPORTPATH/args.date/"MATRIX_TENNIS_RESEARCH_BIOGRAPHY_CROSSWALK_LAST.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in
        ("biographical_id_triplets_matched","total_source_metadata_events",
         "events_with_schedule_conflicts","events_with_match_page_clock_conflicts","events_with_match_page_clock_display_agreement","new_hard_holdout_admissions","new_clay_holdout_admissions")},sort_keys=True))
    if not result["biographical_id_triplets_matched"]:
        raise SystemExit("ZERO_AUTHENTIC_RESEARCH_CROSSWALK_PROOFS")

if __name__ == "__main__":
    main()
