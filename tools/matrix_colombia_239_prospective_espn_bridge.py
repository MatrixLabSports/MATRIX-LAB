"""Prematch ESPN Colombia candidates joined to authenticated October source team crosswalk.

Not canonical: SofaScore and Flashscore must both verify independently, plus
feature equivalence, OOS and market odds. No P_MATRIX, EV, Telegram or betting.
"""
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen

from tools.matrix_colombia_239_original_espn_historic_crosswalk import utc
URL="https://site.api.espn.com/apis/site/v2/sports/soccer/col.1/scoreboard?dates={date}&limit=30"
LIMIT=1500000
DAYS=("20261124","20261125")

def crosswalk_ids(proof):
    if (proof.get("schema")!="MATRIX_COLOMBIA_239_API_ESPN_HISTORIC_IDENTITY_CROSSWALK_V1"
        or proof.get("prospective_cross_provider_fixture_identity_certified") is not False
        or proof.get("production_p_matrix_authorized") is not False
        or proof.get("telegram_signal_authorized") is not False
        or proof.get("real_money")!="BLOCKED"):
        raise ValueError("HISTORICAL_IDENTITY_PROOF_UNTRUSTED")
    mapping={}
    reverse={}
    for row in proof.get("historical_matches",[]):
        if row.get("kickoff_score_orientation_and_name_verified") is not True:
            raise ValueError("HISTORICAL_MATCH_NOT_INDEPENDENTLY_VERIFIED")
        for side in ("home","away"):
            eid=str(row[f"espn_{side}_id"])
            aid=str(row[f"api_{side}_id"])
            if (not eid.isdecimal() or not aid.isdecimal() or
                eid in mapping and mapping[eid]!=aid or
                aid in reverse and reverse[aid]!=eid):
                raise ValueError("CROSSWALK_TEAM_ID_CONTRADICTION")
            mapping[eid]=aid
            reverse[aid]=eid
    if len(mapping)!=proof.get("distinct_original_team_ids_crosswalked"):
        raise ValueError("HISTORICAL_TEAM_CROSSWALK_COUNT_INVALID")
    return mapping

def inspect(raw_by_day,proof,*,observed_at_utc):
    observed=utc(observed_at_utc)
    mapped=crosswalk_ids(proof)
    seen=set();candidates=[];blocked=[]
    shas={}
    for day in DAYS:
        raw=raw_by_day.get(day)
        if not isinstance(raw,bytes):raise ValueError("MISSING_ESPN_NATIVE_RAW_DAY")
        shas[day]=hashlib.sha256(raw).hexdigest()
        payload=json.loads(raw)
        header=payload.get("leagues")
        if (not isinstance(header,list) or len(header)!=1 or
            not isinstance(header[0],dict) or header[0].get("slug")!="col.1"):
            raise ValueError("ESPN_INCORRECT_COMPETITION")
        for event in payload.get("events",[]):
            if not isinstance(event,dict):raise ValueError("ESPN_EVENT_BAD")
            event_id=str(event.get("id") or "")
            if not event_id.isdecimal() or event_id in seen:
                raise ValueError("ESPN_DUPLICATE_PROSPECTIVE_EVENT")
            seen.add(event_id)
            comp=event.get("competitions") or []
            if len(comp)!=1:continue
            state=((comp[0].get("status") or {}).get("type") or {})
            kickoff=utc(event.get("date"))
            if (kickoff<=observed or state.get("completed") is True or
                state.get("name") not in ("STATUS_SCHEDULED","STATUS_PRE")):
                blocked.append({"event_id":event_id,"reason":"NOT_CONFIRMED_FUTURE_SCHEDULED"});continue
            teams={}
            for c in comp[0].get("competitors") or []:
                side=c.get("homeAway")
                team=c.get("team") or {}
                eid=str(team.get("id") or "")
                if side not in ("home","away") or side in teams or not eid.isdecimal():
                    raise ValueError("ESPN_CURRENT_TEAM_ID_OR_ORIENTATION_INVALID")
                teams[side]={"espn_team_id":eid,"name":team.get("displayName"),
                             "original_api_football_239_team_id_historical_hint":mapped.get(eid)}
            if len(teams)!=2 or teams["home"]["espn_team_id"]==teams["away"]["espn_team_id"]:
                raise ValueError("ESPN_CURRENT_DUPLICATE_TEAM")
            if (not teams["home"]["original_api_football_239_team_id_historical_hint"]
                or not teams["away"]["original_api_football_239_team_id_historical_hint"]):
                blocked.append({"event_id":event_id,"reason":"TEAM_NOT_PROVEN_BY_PRIOR_HISTORICAL_CROSSWALK"});continue
            candidates.append({
              "espn_current_fixture_id":event_id,"kickoff_utc":kickoff.isoformat(),
              "home":teams["home"],"away":teams["away"],
              "original_fixture_id":None,
              "sofascore_fixture_match_verified":False,
              "flashscore_fixture_match_verified":False,
              "historic_team_id_crosswalk_verified":True,
              "current_original_api_football_fixture_identity_verified":False,
              "original_enriched_feature_parity_verified":False,
              "production_p_matrix_authorized":False,"telegram_signal_authorized":False})
    return {
       "schema":"MATRIX_COLOMBIA_239_PROSPECTIVE_ESPN_HISTORIC_TEAM_BRIDGE_V1",
       "status":"FREE_SOURCE_PIT_DISCOVERY_ONLY_PENDING_SOFA_FLASH_AND_MODEL_PARITY",
       "source_order":["SOFASCORE","FLASHSCORE","ESPN"],
       "source_received_at_utc":observed.isoformat(),
       "historical_crosswalk_fixture_pairs":proof["exact_historical_fixture_pairs"],
       "historical_crosswalk_team_ids":len(mapped),
       "source_daily_raw_sha256":shas,
       "future_fixtures_with_historic_team_id_bridge":len(candidates),
       "eligible_for_production":0,
       "historically_joined_research_only_fixtures":candidates,
       "blocked":blocked,
       "sofascore_and_flashscore_priority_respected":True,
       "source_feature_parity_certified":False,
       "scientific_oos_certified":False,
       "authentic_bookmaker_and_sharp_quotes_verified":False,
       "production_p_matrix_authorized":False,
       "telegram_signal_authorized":False,
       "automatic_wagering":False,
       "real_money":"BLOCKED"}

def capture(*,opener=urlopen):
    raws={}
    for day in DAYS:
        req=Request(URL.format(date=day),headers={"Accept":"application/json","User-Agent":"MATRIX-Research/1.0"})
        with opener(req,timeout=25) as response:
            if int(response.status)!=200:raise ValueError("ESPN_HTTP_STATUS_INVALID")
            raw=response.read(LIMIT+1)
        if not raw or len(raw)>LIMIT:raise ValueError("ESPN_RAW_BODY_INVALID")
        raws[day]=raw
    return raws,datetime.now(timezone.utc).isoformat()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--crosswalk",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--raw-dir",required=True,type=Path)
    a=p.parse_args()
    if set(a.out.parts)&{"governance","telegram","notifications","daily_prematch_reports"}:
        raise SystemExit("NO_PRODUCTION_WRITES")
    proof=json.loads(a.crosswalk.read_bytes())
    raws,observed=capture()
    result=inspect(raws,proof,observed_at_utc=observed)
    a.raw_dir.mkdir(parents=True,exist_ok=True)
    for day,raw in raws.items():
        dest=a.raw_dir/("ESPN_col_1_"+day+"_"+result["source_daily_raw_sha256"][day]+".json")
        if dest.exists() and dest.read_bytes()!=raw:raise ValueError("ESPN_SOURCE_IMMUTABILITY_VIOLATION")
        dest.write_bytes(raw)
        if hashlib.sha256(dest.read_bytes()).hexdigest()!=result["source_daily_raw_sha256"][day]:
            raise ValueError("ESPN_RAW_SHA_PERSISTENCE_FAILED")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"historical_mapped_team_ids":result["historical_crosswalk_team_ids"],
      "future_research_candidates":result["future_fixtures_with_historic_team_id_bridge"],
      "official_candidates":0,"telegram":False}))
if __name__=="__main__":main()
