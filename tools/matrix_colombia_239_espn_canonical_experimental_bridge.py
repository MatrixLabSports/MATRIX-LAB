"""SHA-bound ESPN 239 history into MATRIX's existing canonical *experimental* input.

Only ESPN matches among the exact 356 original API-Football counterparts
are admitted; both kickoff-conflicted games stay quarantined. No source
provider masquerading, no official p_matrix, no EV, no Telegram, no betting.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
from app.research.football.match_analysis_input import (
    FootballHistoryObservation,FootballMatchAnalysisInput,assess_match_analysis_readiness)
from tools.matrix_colombia_239_original_espn_historic_crosswalk import espn_rows,utc

SCHEMA="MATRIX_COL_239_ESPN_AUTHENTIC_CANONICAL_EXPERIMENTAL_INPUT_V1"
def build(espn_raw,parity,three,shadow):
    if (parity.get("schema")!="MATRIX_COLOMBIA_239_COMPLETE_SEASON_FT_GOALS_AND_FUTURE_IDENTITY_AUDIT_V1"
        or three.get("schema")!="MATRIX_COLOMBIA_239_THREE_SOURCE_RESEARCH_TO_TELEGRAM_GUARD_V1"
        or shadow.get("schema")!="MATRIX_COLOMBIA_239_ORIGINAL_ENGINE_FREE_SOURCE_PIT_SHADOW_V1"
        or hashlib.sha256(espn_raw).hexdigest()!=parity.get("espn_fullseason_raw_sha256")
        or parity.get("exact_original_goals_time_and_team_parity_count")!=356
        or parity.get("original_results_unmatched_count")!=2
        or three.get("three_calendar_matches")!=2
        or shadow.get("original_parameters")!={"a":0.6,"b":0,"c":0.4}
        or any(x.get("real_money")!="BLOCKED" for x in (parity,three,shadow))):
        raise ValueError("EXPERIMENTAL_CANONICAL_INPUT_SOURCE_UNTRUSTED")
    receipt=utc(parity["espn_received_at_utc"])
    matches=parity["historical_matched_fixture_ids"]
    valid_es_ids={str(x["espn_event_id"]) for x in matches}
    if len(matches)!=356:raise ValueError("SOURCE_HISTORICAL_PAIR_SET_INCOMPLETE")
    if len(valid_es_ids)!=len(matches):raise ValueError("DUPLICATE_STRICT_HISTORICAL_MATCH")
    source=json.loads(espn_raw)
    competitions=source.get("leagues") or []
    if len(competitions)!=1 or competitions[0].get("slug")!="col.1":
        raise ValueError("WRONG_SOURCE_LEAGUE")
    scored={str(x["espn_event_id"]):x for x in shadow["research_scores"]}
    source_events={str(x["id"]):x for x in source.get("events") or []}
    history=[x for x in espn_rows(espn_raw) if x["id"] in valid_es_ids]
    if len(history)!=356:raise ValueError("SOURCE_HISTORICAL_PAIR_SET_INCOMPLETE")
    history.sort(key=lambda x:(x["kickoff"],x["id"]))
    result=[]
    for matched in three["three_source_matches"]:
        eid=str(matched["espn_event_id"])
        forecast=scored.get(eid)
        native=source_events.get(eid)
        if (not forecast or not native or
            matched.get("source_fixture_identity_on_three_calendars_verified") is not True):
            raise ValueError("CURRENT_TARGET_NOT_AUTHENTICATED")
        as_of=utc(forecast["scored_at_utc"])
        kickoff=utc(matched["kickoff_utc"])
        if as_of<receipt or as_of>=kickoff or kickoff!=utc(forecast["kickoff_utc"]):
            raise ValueError("EXPERIMENTAL_CANONICAL_POINT_IN_TIME_FAIL")
        sides={}
        for s in native.get("competitions",[{}])[0].get("competitors",[]):
            side=s.get("homeAway")
            if side not in ("home","away") or side in sides:
                raise ValueError("CURRENT_TEAM_ORIENTATION_INVALID")
            team=s.get("team") or {}
            if not str(team.get("id","")).isdigit() or not team.get("displayName"):
                raise ValueError("CURRENT_NATIVE_TEAM_ID_INVALID")
            sides[side]={"id":str(team["id"]),"name":str(team["displayName"])}
        if len(sides)!=2 or sides["home"]["id"]==sides["away"]["id"]:
            raise ValueError("CURRENT_TWO_TEAMS_REQUIRED")
        histories={}
        for side in ("home","away"):
            team=sides[side]
            teamhist=[]
            for old in history:
                if (team["id"] not in (old["home_id"],old["away_id"])
                    or old["kickoff"]>=kickoff or old["kickoff"]>=receipt):
                    continue
                ownhome=old["home_id"]==team["id"]
                opponent=sides["away" if side=="home" else "home"]
                oldopponent=old["away_id"] if ownhome else old["home_id"]
                historic_native=source_events.get(old["id"])
                if not historic_native or len(historic_native.get("competitions") or [])!=1:
                    raise ValueError("NATIVE_HISTORIC_EVENT_NOT_PROVEN")
                opponent_names=[
                    x.get("team",{}).get("displayName")
                    for x in historic_native["competitions"][0].get("competitors") or []
                    if str(x.get("team",{}).get("id"))==str(oldopponent)]
                if len(opponent_names)!=1 or not opponent_names[0]:
                    raise ValueError("AUTHENTIC_OPPONENT_NAME_MISSING")
                teamhist.append(FootballHistoryObservation(
                  fixture_id=old["id"],
                  kickoff_utc=old["kickoff"].isoformat(),
                  team_id=team["id"],team_name=team["name"],
                  opponent_id=oldopponent,opponent_name=str(opponent_names[0]),
                  venue_role="home" if ownhome else "away",
                  goals_for=old["home_goals"] if ownhome else old["away_goals"],
                  goals_against=old["away_goals"] if ownhome else old["home_goals"],
                  competition="COL_PRIMERA_A",source_provider="ESPN_COL_1",
                  observed_at_utc=receipt.isoformat(),
                  source_payload_sha256=parity["espn_fullseason_raw_sha256"],
                  fixture_identity_kind="provider",
                  source_team_id=team["id"],source_opponent_id=oldopponent,
                  source_reference=parity["espn_fullseason_source_url"]))
            histories[side]=tuple(teamhist[-20:])
        obj=FootballMatchAnalysisInput(
          benchmark_id="MATRIX_COL_239_2026_ESPN_EXP_ONLY",
          target_key="COL239:ESPN:"+eid,fixture_id=eid,
          as_of_utc=as_of.isoformat(),kickoff_utc=kickoff.isoformat(),
          home_team_id=sides["home"]["id"],home_team_name=sides["home"]["name"],
          away_team_id=sides["away"]["id"],away_team_name=sides["away"]["name"],
          competition_id="239",competition_name="COLOMBIA_PRIMERA_A",season=2026,
          round_name=None,venue_name=None,
          fixture_source_provider="ESPN_COL_1",
          fixture_payload_sha256=parity["espn_fullseason_raw_sha256"],
          fixture_id_namespace="ESPN_COL_1",
          home_team_id_namespace="ESPN_COL_1",
          away_team_id_namespace="ESPN_COL_1",
          home_history=histories["home"],away_history=histories["away"])
        ready=assess_match_analysis_readiness(obj)
        result.append({"espn_fixture_id":eid,"canonical_analysis_input_sha256":obj.canonical_sha256(),
          "fixture_observed_at_utc":receipt.isoformat(),
          "home_history_count":len(histories["home"]),
          "away_history_count":len(histories["away"]),
          "structural_readiness":ready.status,
          "canonical_source_namespace":"ESPN_COL_1",
          "original_api_football_fixture_id":None,
          "original_feature_equivalence_certified":False,
          "official_p_matrix_authorized":False,
          "telegram_signal_authorized":False})
    return {"schema":SCHEMA,"status":"EXPERIMENTAL_CANONICAL_INPUTS_READY_FOR_STRUCTURAL_ASSESSMENT_ONLY",
      "original_october_strict_matched_history":len(history),
      "historical_kickoff_conflicts_still_quarantined":2,
      "original_enriched_feature_equivalence_certified":False,
      "prospective_oos_certified":False,
      "input_count":len(result),"inputs":result,
      "source_sha256":hashlib.sha256(espn_raw).hexdigest(),
      "source_provider":"ESPN_COL_1","production_p_matrix_authorized":False,
      "telegram_signal_authorized":False,"real_money":"BLOCKED","automatic_wagering":False}
def main():
    p=argparse.ArgumentParser()
    for key in ("espn-gz","parity","three","shadow","out"):
        p.add_argument("--"+key,required=True,type=Path)
    args=p.parse_args()
    load=lambda path:json.loads(path.read_bytes())
    result=build(gzip.decompress(args.espn_gz.read_bytes()),load(args.parity),load(args.three),load(args.shadow))
    if any(x in args.out.parts for x in ("telegram","governance","notifications")):
        raise SystemExit("RESEARCH_ONLY_CANONICAL_INPUT_OUTPUT")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"structural_compatibility_count":result["input_count"],
      "official_p_matrix":False,"telegram":False}))
if __name__=="__main__":main()
