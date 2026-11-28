"""Complete 2026 Colombia Primera A ESPN↔original goals reconciliation.

Original API-Football October archive is immutable. ESPN's current public
season bytes are SHA-bound and compressed, mismatches quarantined. No
backfilled prospective predictions, bookmaker prices, Telegram or real money.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from tools.matrix_colombia_239_original_espn_historic_crosswalk import (
    ARCHIVE,original_rows,espn_rows,utc,
)

URL="https://site.api.espn.com/apis/site/v2/sports/soccer/col.1/scoreboard?dates=2026&limit=500"
MAX_BYTES=8_000_000
def team_map(crosswalk):
    if (crosswalk.get("schema")!="MATRIX_COLOMBIA_239_API_ESPN_HISTORIC_IDENTITY_CROSSWALK_V1"
        or crosswalk.get("exact_historical_fixture_pairs",0)<2
        or crosswalk.get("production_p_matrix_authorized") is not False
        or crosswalk.get("telegram_signal_authorized") is not False):
        raise ValueError("UNTRUSTED_HISTORICAL_PROOF")
    mapping={};inverse={}
    for row in crosswalk.get("historical_matches",[]):
        if row.get("kickoff_score_orientation_and_name_verified") is not True:
            raise ValueError("CROSSWALK_HISTORIC_PAIR_NOT_PROVEN")
        for side in ("home","away"):
            k=str(row[f"espn_{side}_id"]);v=str(row[f"api_{side}_id"])
            if (k in mapping and mapping[k]!=v or
                v in inverse and inverse[v]!=k):
                raise ValueError("CROSSWALK_TEAM_ID_CONTRADICTION")
            mapping[k]=v;inverse[v]=k
    if len(mapping)!=crosswalk["distinct_original_team_ids_crosswalked"]:
        raise ValueError("CROSSWALK_TEAM_COUNT_INVALID")
    return mapping

def inspect(original_raw,espn_raw,crosswalk,received_at_utc):
    observed=utc(received_at_utc)
    before=original_rows(original_raw)
    events=espn_rows(espn_raw)
    mapping=team_map(crosswalk)
    original_index={}
    for o in before:
        ident=(o["home_id"],o["away_id"])
        original_index.setdefault(ident,[]).append(o)
    matched=[];unmatched=[];used=set()
    archive_cutoff=utc("2026-10-28T05:41:28Z")
    for e in events:
        if e["kickoff"]>=archive_cutoff:continue
        hid=mapping.get(e["home_id"]);aid=mapping.get(e["away_id"])
        eligible=[x for x in original_index.get((hid,aid),[])
            if abs((x["kickoff"]-e["kickoff"]).total_seconds())<=60
            and x["home_goals"]==e["home_goals"]
            and x["away_goals"]==e["away_goals"]]
        if len(eligible)!=1:
            unmatched.append({"espn_event_id":e["id"],"kickoff_utc":e["kickoff"].isoformat(),
              "home":e["home"],"away":e["away"],
              "reason":"NO_EXACT_ORIGINAL_ID_TIME_AND_FINAL_SCORE_MATCH"})
            continue
        o=eligible[0]
        if o["id"] in used:raise ValueError("ORIGINAL_MATCH_REUSED_MULTIPLE_TIMES")
        used.add(o["id"])
        matched.append({"original_fixture_id":o["id"],"espn_event_id":e["id"],
          "kickoff_utc":e["kickoff"].isoformat(),"home_goals":e["home_goals"],
          "away_goals":e["away_goals"]})
    originals_missing=[x["id"] for x in before if x["id"] not in used]
    # The future fixture list is a source observation only, not a same-fixture
    # original crosswalk. No historic result newer than the response receipt
    # can enter the model (no assumed availability of any unobserved results).
    source=json.loads(espn_raw)
    future=[];blocked=[]
    for item in source.get("events",[]):
        if not isinstance(item,dict):continue
        comps=item.get("competitions") or []
        if len(comps)!=1:continue
        comp=comps[0];state=(comp.get("status") or {}).get("type") or {}
        if state.get("name") not in ("STATUS_SCHEDULED","STATUS_PRE") or state.get("completed") is True:continue
        kickoff=utc(item.get("date"))
        if kickoff<=observed:continue
        sides={}
        for obj in comp.get("competitors") or []:
            team=obj.get("team") or {}
            kind=obj.get("homeAway")
            if kind in ("home","away") and kind not in sides:
                sid=str(team.get("id") or "")
                sides[kind]={"espn_team_id":sid,"team_name":team.get("displayName"),
                    "original_api_football_team_id_from_history":mapping.get(sid)}
        if len(sides)!=2:continue
        row={"espn_current_fixture_id":str(item.get("id") or ""),
            "kickoff_utc":kickoff.isoformat(),"home":sides["home"],"away":sides["away"],
            "original_api_football_current_fixture_id":None,
            "sofascore_current_identity_verified":False,
            "flashscore_current_identity_verified":False,
            "original_model_p_matrix_official":False}
        if any(not x["original_api_football_team_id_from_history"] for x in sides.values()):
            blocked.append({"espn_current_fixture_id":row["espn_current_fixture_id"],
                            "reason":"NOT_ALL_TEAMS_IN_AUTHENTIC_HISTORICAL_IDENTITY_CROSSWALK"})
        else:future.append(row)
    return {
      "schema":"MATRIX_COLOMBIA_239_COMPLETE_SEASON_FT_GOALS_AND_FUTURE_IDENTITY_AUDIT_V1",
      "status":"HISTORIC_GOAL_SCORE_CONCORDANCE_WITH_QUARANTINED_MISMATCHES_AND_RESEARCH_FUTURES",
      "source_order":["SOFASCORE","FLASHSCORE","ESPN_AFTER_BROWSER"],
      "original_archive_sha256":hashlib.sha256(original_raw).hexdigest(),
      "espn_fullseason_raw_sha256":hashlib.sha256(espn_raw).hexdigest(),
      "espn_fullseason_raw_bytes":len(espn_raw),
      "espn_fullseason_source_url":URL,
      "espn_received_at_utc":observed.isoformat(),
      "historical_team_ids_one_to_one_crosswalked":len(mapping),
      "original_october_asof_finished_fixture_count":len(before),
      "espn_fullseason_finished_fixture_count":len(events),
      "exact_original_goals_time_and_team_parity_count":len(matched),
      "original_results_unmatched_count":len(originals_missing),
      "historical_matched_fixture_ids":matched,
      "original_unmatched_fixture_ids":originals_missing,
      "espn_before_archive_cutoff_mismatch_details":unmatched,
      "future_research_discovery_count":len(future),
      "future_native_team_identity_bridged_rows":future,
      "future_missing_team_identity_rows":blocked,
      "historic_hard_fail_on_unmatched_for_production":True,
      "point_in_time_source_receipt_not_backdated":True,
      "historical_matches_not_backfilled_as_prospective_predictions":True,
      "all_source_historical_rows_equivalent":len(originals_missing)==0 and len(unmatched)==0,
      "original_enriched_feature_equivalence_certified":False,
      "prospective_source_equivalence_certified":False,
      "scientific_oos_certified":False,
      "current_sofascore_and_flashscore_identity_verified":False,
      "authentic_bookmaker_and_sharp_quote_pair_verified":False,
      "production_p_matrix_authorized":False,
      "telegram_signal_authorized":False,
      "automatic_wagering":False,
      "real_money":"BLOCKED",
    }

def capture(opener=urlopen):
    req=Request(URL,headers={"Accept":"application/json","User-Agent":"MATRIX-Research/1.0"})
    with opener(req,timeout=30) as resp:
        if int(resp.status)!=200:raise ValueError("ESPN_SOURCE_HTTP_FAILURE")
        raw=resp.read(MAX_BYTES+1)
    if not raw or len(raw)>MAX_BYTES:raise ValueError("ESPN_SOURCE_SIZE_INVALID")
    return raw,datetime.now(timezone.utc).isoformat()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,default=ARCHIVE)
    p.add_argument("--crosswalk",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--compressed-source",type=Path,required=True)
    args=p.parse_args()
    if set(args.out.parts)&{"telegram","governance","daily_prematch_reports","notifications"}:
        raise SystemExit("RESEARCH_ONLY_OUTPUT")
    original=args.archive.read_bytes()
    proof=json.loads(args.crosswalk.read_bytes())
    espn,stamp=capture()
    doc=inspect(original,espn,proof,stamp)
    args.compressed_source.parent.mkdir(parents=True,exist_ok=True)
    compressed=gzip.compress(espn,mtime=0)
    args.compressed_source.write_bytes(compressed)
    if hashlib.sha256(gzip.decompress(args.compressed_source.read_bytes())).hexdigest()!=doc["espn_fullseason_raw_sha256"]:
        raise SystemExit("ESPN_ARCHIVE_SHA_MISMATCH")
    doc["gzip_raw_archive_path"]=args.compressed_source.as_posix()
    doc["gzip_archive_sha256"]=hashlib.sha256(compressed).hexdigest()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(doc,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"original_goal_match_pairs":doc["exact_original_goals_time_and_team_parity_count"],
      "original_results_mismatch":doc["original_results_unmatched_count"],
      "historical_teams":doc["historical_team_ids_one_to_one_crosswalked"],
      "future_team_bridge":doc["future_research_discovery_count"],"production":False},sort_keys=True))
if __name__=="__main__":main()
