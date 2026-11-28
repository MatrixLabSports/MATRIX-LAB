"""Auditable free-source feasibility for the three enrichment workstreams.

This is NOT a claim that these are the unnamed 3/11 numeric discrepancies:
the historical 8/11 summary does not include a feature-by-feature diff.
Never equate post-game API responses with evidence known at prematch freeze.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

WORKSTREAMS={
 "home_history": "Provider-native completed history of the target home team, >=5 rows",
 "away_history": "Provider-native completed history of the target away team, >=5 rows",
 "prematch_lineage": "Provider-native crosswalk, observation timestamp and payload hash known at freeze",
}

def utc(raw):
    dt=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    if dt.utcoffset() is None:
        raise ValueError("ENRICHED_PIT_TIMESTAMP_NOT_AWARE")
    return dt.astimezone(timezone.utc)

def evaluate_free_matches(payload:dict,*,home_id:str,away_id:str,as_of_utc:str,target_kickoff_utc:str)->dict:
    """Research-only row feasibility. Reject ambiguous or retrospectively captured data."""
    as_of,target=utc(as_of_utc),utc(target_kickoff_utc)
    if not as_of<target:
        raise ValueError("ENRICHED_PIT_NOT_BEFORE_KICKOFF")
    if not isinstance(payload,dict) or not isinstance(payload.get("matches"),list):
        raise ValueError("FREE_MATCH_RESPONSE_INVALID")
    rows_by_team={home_id:[],away_id:[]}
    failures={"missing_last_updated":0,"updated_after_freeze":0,"invalid_identity":0,
              "invalid_score":0,"not_finished_before_freeze":0}
    for row in payload["matches"]:
        if not isinstance(row,dict):
            continue
        home,away=row.get("homeTeam") or {},row.get("awayTeam") or {}
        try:
            hid,aid=str(home["id"]),str(away["id"])
            if hid==aid or not hid or not aid:
                raise ValueError("BAD_TEAM_ID")
            event=utc(row["utcDate"])
        except (ValueError,KeyError,TypeError,AttributeError):
            failures["invalid_identity"]+=1
            continue
        sides={hid,aid}&set(rows_by_team)
        if not sides:continue
        if row.get("status")!="FINISHED" or not event<as_of:
            failures["not_finished_before_freeze"]+=1
            continue
        score=(row.get("score") or {}).get("fullTime") or {}
        hg,ag=score.get("home"),score.get("away")
        if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in (hg,ag)):
            failures["invalid_score"]+=1
            continue
        updated=row.get("lastUpdated")
        if not updated:
            failures["missing_last_updated"]+=1
            continue
        try:
            last_updated=utc(updated)
        except (TypeError,ValueError):
            failures["missing_last_updated"]+=1
            continue
        if last_updated>as_of:
            failures["updated_after_freeze"]+=1
            continue
        for team in sides:
            rows_by_team[team].append({
                "source_match_id":str(row.get("id") or ""),
                "kickoff_utc":event.isoformat(),"last_updated_utc":last_updated.isoformat(),
                "goals_for":hg if team==hid else ag,
                "goals_against":ag if team==hid else hg,
                "venue_role":"home" if team==hid else "away"
            })
    def unique(items):
        keyed={}
        for row in sorted(items,key=lambda r:(r["kickoff_utc"],r["source_match_id"]),reverse=True):
            if row["source_match_id"]:
                keyed[row["source_match_id"]]=row
        return sorted(keyed.values(),key=lambda r:r["kickoff_utc"],reverse=True)
    h,a=unique(rows_by_team[home_id]),unique(rows_by_team[away_id])
    return {
       "schema":"MATRIX_FREE_ENRICHED_PIT_FEASIBILITY_V1",
       "status":"RESEARCH_ONLY_NOT_CERTIFIED",
       "workstreams":{
         "home_history":{"required":5,"observed_eligible_count":len(h),"minimum_count_met":len(h)>=5},
         "away_history":{"required":5,"observed_eligible_count":len(a),"minimum_count_met":len(a)>=5},
         "prematch_lineage":{"observed_free_response_hash":hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
           "cross_provider_fixture_identity_verified":False,
           "original_api_football_enriched_pit_parity_verified":False,
           "capture_at_freeze_verified":False}
       },
       "rejections":failures,
       "last_updated_not_proof_of_original_capture":True,
       "provider_native_original_pit_rows_verified":False,
       "eleven_feature_diff_present":False,
       "the_three_workstreams_are_not_claimed_as_three_unmatched_features":True,
       "p_matrix":None,"telegram_signal_authorized":False,
       "automatic_wagering":False,"real_money":"BLOCKED"
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--home-id",required=True)
    parser.add_argument("--away-id",required=True)
    parser.add_argument("--as-of-utc",required=True)
    parser.add_argument("--kickoff-utc",required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if "daily_prematch_reports" in args.out.parts:
        raise SystemExit("RESEARCH_MUST_NOT_WRITE_CANONICAL")
    result=evaluate_free_matches(json.loads(args.source.read_text(encoding="utf-8")),
      home_id=args.home_id,away_id=args.away_id,as_of_utc=args.as_of_utc,
      target_kickoff_utc=args.kickoff_utc)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"workstreams":result["workstreams"],"real_money":"BLOCKED"}))

if __name__=="__main__":
    main()
