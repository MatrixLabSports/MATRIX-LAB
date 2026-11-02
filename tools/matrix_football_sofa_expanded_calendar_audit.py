"""Conservative world-calendar crosscheck for physical SofaScore Opera evidence.

Does not claim that every visible match is model-covered, worldwide complete, or
quotable. Protects the eight pre-registered Sofa/Flash/independent identities.
Never modifies calibrated MATRIX probabilities or Telegram.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATE = "2026-11-02"
BOGOTA = ZoneInfo("America/Bogota")
SOURCE_ORDER = ["SOFASCORE", "FLASHSCORE", "APIS"]
SCHEMA = "MATRIX_OPERA_FOOTBALL_FULL_LINK_CAPTURE_V1"
MATCH_LINK = re.compile(r"^https://www\.sofascore\.com/es/football/match/[^\s#]+#id:(\d+)$")
DATE_LABEL = re.compile(r"^2/11/26\s+(\d{1,2}):(\d\d)(?:\s|$)")

def reconcile(capture: dict, sofa: dict, independent: dict, flash: dict) -> dict:
    if not all(isinstance(x,dict) for x in (capture,sofa,independent,flash)):
        raise ValueError("CAPTURE_AND_REFERENCE_OBJECTS_REQUIRED")
    if [capture.get("schema"),sofa.get("schema"),independent.get("schema"),flash.get("schema")] != [
        SCHEMA, "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK_V1",
        "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1", "MATRIX_FLASH_FOOTBALL_CROSSCHECK_V1"
    ]:
        raise ValueError("SOURCE_SCHEMA_INVALID")
    if any(x.get("target_date_bogota") != DATE for x in (capture,sofa,independent,flash)):
        raise ValueError("SOURCE_DATE_MISMATCH")
    if any(x.get("real_money") != "BLOCKED" for x in (capture,sofa,independent,flash)):
        raise ValueError("REAL_MONEY_NOT_BLOCKED")
    if any(x.get("source_order") != SOURCE_ORDER for x in (capture,sofa,independent,flash)):
        raise ValueError("SOURCE_ORDER_MISMATCH")
    if capture.get("source")!="SOFASCORE":
        raise ValueError("PRIMARY_SOFA_SOURCE_REQUIRED")
    if (capture.get("telegram_authorized") is not False or
        capture.get("probability_authorized") is not False or
        capture.get("automatic_wagering") is not False):
        raise ValueError("SOURCE_CAPTURE_NOT_FAIL_CLOSED")
    if (sofa.get("status")!="PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL" or
        flash.get("status")!="PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS" or
        flash.get("flashscore_verified") is not True or
        sofa.get("rejected_count") or flash.get("rejected_count") or
        sofa.get("signal_generation_authorized") is not False or
        flash.get("signal_generation_authorized") is not False or
        independent.get("signal_generation_authorized") is not False):
        raise ValueError("PREVIOUS_CROSS_SOURCE_IDENTITY_NOT_CERTIFIED")
    observations = capture.get("observations")
    if not isinstance(observations,list) or capture.get("observed_link_count") != len(observations):
        raise ValueError("PHYSICAL_OBSERVATION_COUNT_MISMATCH")
    by_id = {}
    dated = []
    not_dated = []
    for item in observations:
        if not isinstance(item,dict):
            raise ValueError("INVALID_OBSERVATION")
        url=str(item.get("source_url") or "")
        m=MATCH_LINK.fullmatch(url)
        if m is None or m.group(1)!=str(item.get("source_event_id") or ""):
            raise ValueError("SOFASCORE_URL_ID_INVALID")
        fid=m.group(1)
        if fid in by_id:
            raise ValueError("SOFA_DUPLICATE_EVENT_ID")
        by_id[fid]=item
        name=str(item.get("display_name") or "")
        dm=DATE_LABEL.match(name)
        if item.get("explicit_target_date_label") is not bool(dm):
            raise ValueError("EXPLICIT_DATE_FLAG_NOT_PHYSICAL")
        if dm is None:
            not_dated.append({"sofascore_event_id":fid,"reason":"EXPLICIT_TARGET_DATE_NOT_VISIBLE"})
        else:
            hh,mm=map(int,dm.groups())
            if hh>23 or mm>59:
                raise ValueError("INVALID_VISIBLE_BOGOTA_TIME")
            dated.append(fid)
    if (capture.get("explicit_target_date_label_count")!=len(dated)
        or capture.get("without_explicit_target_date_count")!=len(not_dated)):
        raise ValueError("SOURCE_DATE_LABEL_COUNTS_MISMATCH")
    official_by_id = {str(x["source_fixture_id"]):x for x in independent.get("fixtures",[]) if isinstance(x,dict)}
    sofa_by_id = {str(x["fixture_id"]):x for x in sofa.get("matched",[]) if isinstance(x,dict)}
    flash_by_id = {str(x["source_fixture_id"]):x for x in flash.get("matched",[]) if isinstance(x,dict)}
    if len(official_by_id)!=len(independent.get("fixtures",[])):
        raise ValueError("DUPLICATE_INDEPENDENT_ID")
    if len(sofa_by_id)!=sofa.get("matched_count") or len(flash_by_id)!=flash.get("matched_count"):
        raise ValueError("REFERENCE_MATCH_COUNT_MISMATCH")
    if not (set(sofa_by_id)==set(flash_by_id)==set(official_by_id)):
        raise ValueError("TRIPLE_REFERENCE_FIXTURE_ID_MISMATCH")
    confirmed=[];rejected=[]
    for independent_id in sorted(official_by_id):
        s=sofa_by_id[independent_id]
        f=flash_by_id[independent_id]
        event_id=str(s.get("sofascore_event_id") or "")
        x=by_id.get(event_id)
        reason=None
        if x is None:
            reason="SOFA_EVENT_NOT_PRESENT_IN_OBSERVED_CALENDAR"
        elif not x["explicit_target_date_label"]:
            reason="SOURCE_EVENT_DATE_NOT_EXPLICIT"
        else:
            try:
                timestamp=datetime.fromisoformat(official_by_id[independent_id]["kickoff_utc"].replace("Z","+00:00"))
                if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                    raise ValueError("KICKOFF_NO_TZ")
                kickoff_utc=timestamp.astimezone(timezone.utc).isoformat()
                local=timestamp.astimezone(BOGOTA)
                m=DATE_LABEL.match(x["display_name"])
                clock=f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
                if local.date().isoformat()!=DATE or local.strftime("%H:%M")!=clock:
                    reason="SOFA_VISIBLE_LOCAL_KICKOFF_MISMATCH"
                elif (s.get("kickoff_utc")!=kickoff_utc or
                      f.get("kickoff_utc")!=kickoff_utc or
                      str(f.get("sofascore_event_id"))!=event_id):
                    reason="CROSS_PROVIDER_TIME_OR_ID_MISMATCH"
            except (ValueError,KeyError,TypeError,AttributeError):
                reason="INVALID_KICKOFF_OR_CALENDAR_TIME"
        if reason:
            rejected.append({"source_fixture_id":independent_id,"sofascore_event_id":event_id,"reason":reason})
        else:
            confirmed.append({"source_fixture_id":independent_id,"sofascore_event_id":event_id,
                              "sofascore_url":x["source_url"],"kickoff_utc":kickoff_utc,
                              "flashscore_mid":f["flashscore_mid"],
                              "calendar_identity_date_and_time_verified":True})
    confirmed_ids={x["sofascore_event_id"] for x in confirmed}
    remaining=[fid for fid in dated if fid not in confirmed_ids]
    status = "PASS_8_TRIPLE_SOURCE_MATCHES_ONLY_WIDER_SOFASCORE_BACKLOG" if (
        not rejected and len(confirmed)==8 and len(official_by_id)==8
    ) else "BLOCKED_PRE_REGISTERED_TRIPLE_SOURCE_DISAGREEMENT"
    return {
        "schema":"MATRIX_FOOTBALL_20261102_OPERA_SOFASCORE_EXPANDED_RECONCILIATION_V1",
        "target_date_bogota":DATE,"generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":status,"source_order":SOURCE_ORDER,
        "observed_visible_links":len(observations),
        "explicit_date_labeled_links":len(dated),
        "without_explicit_date_label":len(not_dated),
        "pre_registered_triple_source_matches":len(confirmed),
        "pre_registered_rejections":rejected,
        "review_only_sofascore_links_without_independent_fixture":len(remaining),
        "unmatched_links_are_not_calibrated_candidates":True,
        "pre_registered_confirmed":confirmed,
        "unmatched_event_ids_for_future_discovery":remaining,
        "undated_event_observations":not_dated,
        "full_world_schedule_certified":False,
        "full_world_api_coverage_certified":False,
        "independent_history_for_unmatched_links_verified":False,
        "over25_exact_market_quote_verified":False,
        "probability_generation_authorized":False,
        "telegram_signals_authorized":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }

def main() -> None:
    ap=argparse.ArgumentParser()
    for key in ("capture","sofa","independent","flash","out"):
        ap.add_argument("--"+key,required=True,type=Path)
    args=ap.parse_args()
    load=lambda p:json.loads(p.read_text(encoding="utf-8"))
    result=reconcile(load(args.capture),load(args.sofa),load(args.independent),load(args.flash))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","observed_visible_links",
                  "explicit_date_labeled_links","pre_registered_triple_source_matches",
                  "review_only_sofascore_links_without_independent_fixture",
                  "telegram_signals_authorized")},sort_keys=True))
    if result["pre_registered_rejections"]:
        raise SystemExit("TRIPLE_SOURCE_CALENDAR_DISAGREEMENT")

if __name__=="__main__":
    main()
