"""Historical API-Football 239 ↔ ESPN col.1 identity crosswalk.

This checks *completed historical* results only. Never retrospectively creates a
prematch forecast or grants current-source feature parity / Telegram eligibility.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

ARCHIVE=Path("evidence/api_football/prospective_daily/2026-10-28/20261028T054128Z/history/raw/league_239_season_2026.bin")
URL="https://site.api.espn.com/apis/site/v2/sports/soccer/col.1/scoreboard?dates=20261027&limit=30"
MAX_BYTES=2_000_000
# Only source names actually verified for the two historical 27 Oct games.
# Never generalize these aliases across countries/leagues or use fuzzy matching.
VERIFIED_ESPN_NAME_ALIASES={
    "cucuta deportivo":"cucuta",
    "boyaca chico fc":"chico",
    "atletico junior":"junior",
}
def norm(name):
    s=unicodedata.normalize("NFKD",str(name or "").casefold())
    return re.sub(r"[^a-z0-9]+"," ","".join(c for c in s if not unicodedata.combining(c))).strip()
def aligned(espn_name,original_name):
    n=norm(espn_name)
    return VERIFIED_ESPN_NAME_ALIASES.get(n,n)==norm(original_name)
def utc(v):
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:raise ValueError("TIMESTAMP_NOT_UTC_AWARE")
    return d.astimezone(timezone.utc)
def original_rows(raw):
    doc=json.loads(raw)
    if str(doc.get("parameters",{}).get("league"))!="239" or str(doc.get("parameters",{}).get("season"))!="2026":
        raise ValueError("ORIGINAL_COLOMBIA_ARCHIVE_HEADER_INVALID")
    rows=[];seen=set()
    for e in doc.get("response",[]):
        if str((e.get("league") or {}).get("id"))!="239":raise ValueError("ORIGINAL_LEAGUE_WRONG")
        f=e.get("fixture") or {}
        if (f.get("status") or {}).get("short")!="FT":continue
        fid=str(f.get("id") or "")
        if not fid.isdecimal() or fid in seen:raise ValueError("ORIGINAL_DUPLICATE_OR_BAD_FIXTURE_ID")
        seen.add(fid)
        h=(e.get("teams") or {}).get("home") or {}
        a=(e.get("teams") or {}).get("away") or {}
        g=e.get("goals") or {}
        if not str(h.get("id") or "").isdigit() or not str(a.get("id") or "").isdigit():continue
        if type(g.get("home")) is not int or type(g.get("away")) is not int:continue
        rows.append({"id":fid,"kickoff":utc(f["date"]),"home_id":str(h["id"]),"away_id":str(a["id"]),
                     "home":h["name"],"away":a["name"],"home_goals":g["home"],"away_goals":g["away"]})
    return rows
def espn_rows(raw):
    doc=json.loads(raw)
    leagues=doc.get("leagues")
    if not isinstance(leagues,list) or len(leagues)!=1 or leagues[0].get("slug")!="col.1":
        raise ValueError("ESPN_WRONG_COLOMBIA_COMPETITION")
    rows=[];seen=set()
    for e in doc.get("events",[]):
        eid=str(e.get("id") or "")
        if not eid.isdecimal() or eid in seen:raise ValueError("ESPN_DUPLICATE_OR_INVALID_EVENT")
        seen.add(eid)
        comps=e.get("competitions") or []
        if len(comps)!=1:continue
        c=comps[0]
        status=((c.get("status") or {}).get("type") or {})
        if status.get("name")!="STATUS_FULL_TIME" or status.get("completed") is not True:continue
        sides={}
        for side in c.get("competitors") or []:
            direction=side.get("homeAway")
            if direction not in ("home","away") or direction in sides:
                raise ValueError("ESPN_DUPLICATE_OR_INVALID_DIRECTION")
            team=side.get("team") or {}
            sid=str(team.get("id") or "")
            try:
                score=int(side.get("score"))
                if str(score)!=str(side.get("score")) or score<0:continue
            except (ValueError,TypeError):continue
            if not sid.isdecimal() or not team.get("displayName"):continue
            sides[direction]={"id":sid,"name":team["displayName"],"score":score}
        if len(sides)!=2 or sides["home"]["id"]==sides["away"]["id"]:continue
        rows.append({"id":eid,"kickoff":utc(e["date"]),"home_id":sides["home"]["id"],
            "away_id":sides["away"]["id"],"home":sides["home"]["name"],"away":sides["away"]["name"],
            "home_goals":sides["home"]["score"],"away_goals":sides["away"]["score"]})
    return rows

def compare(original_raw,espn_raw,received_at):
    stamp=utc(received_at)
    originals=original_rows(original_raw)
    espn=espn_rows(espn_raw)
    identities=[];reject=[];seen_orig=set();seen_espn=set();original_to_espn={};espn_to_original={}
    for candidate in espn:
        if candidate["kickoff"]>=stamp:
            reject.append({"espn_id":candidate["id"],"reason":"ESPN_MATCH_AFTER_RECEIPT"});continue
        pool=[x for x in originals if abs((x["kickoff"]-candidate["kickoff"]).total_seconds())<=60
              and x["home_goals"]==candidate["home_goals"]
              and x["away_goals"]==candidate["away_goals"]
              and aligned(candidate["home"],x["home"])
              and aligned(candidate["away"],x["away"])]
        if len(pool)!=1:
            reject.append({"espn_id":candidate["id"],"reason":"NO_UNIQUE_TIME_SCORE_AND_NAME_PAIR"});continue
        x=pool[0]
        if x["id"] in seen_orig or candidate["id"] in seen_espn:
            raise ValueError("CROSSWALK_DUPLICATE_MATCH")
        for api_id,espn_id in [(x["home_id"],candidate["home_id"]),(x["away_id"],candidate["away_id"])]:
            if (api_id in original_to_espn and original_to_espn[api_id]!=espn_id
                or espn_id in espn_to_original and espn_to_original[espn_id]!=api_id):
                raise ValueError("CROSSWALK_TEAM_ID_CONTRADICTION")
            original_to_espn[api_id]=espn_id
            espn_to_original[espn_id]=api_id
        seen_orig.add(x["id"]);seen_espn.add(candidate["id"])
        identities.append({"original_api_football_fixture_id":x["id"],"espn_event_id":candidate["id"],
         "kickoff_utc":x["kickoff"].isoformat(),"api_home_id":x["home_id"],
         "espn_home_id":candidate["home_id"],"api_away_id":x["away_id"],"espn_away_id":candidate["away_id"],
         "home_original":x["home"],"home_espn":candidate["home"],"away_original":x["away"],
         "away_espn":candidate["away"],"home_goals":x["home_goals"],"away_goals":x["away_goals"],
         "kickoff_score_orientation_and_name_verified":True,
         "historical_only_not_future_identity":True})
    return {"schema":"MATRIX_COLOMBIA_239_API_ESPN_HISTORIC_IDENTITY_CROSSWALK_V1",
      "status":"HISTORIC_IDENTITY_AUDIT_ONLY_NOT_PROSPECTIVE_MODEL_PARITY",
      "source_order":["SOFASCORE","FLASHSCORE","ESPN_PUBLIC_AFTER_BROWSER"],
      "original_archive_path":str(ARCHIVE),
      "original_archive_sha256":hashlib.sha256(original_raw).hexdigest(),
      "espn_source_url":URL,"espn_response_sha256":hashlib.sha256(espn_raw).hexdigest(),
      "espn_response_received_at_utc":stamp.isoformat(),
      "original_finished_history_rows":len(originals),
      "espn_finished_event_rows":len(espn),
      "exact_historical_fixture_pairs":len(identities),
      "distinct_original_team_ids_crosswalked":len(original_to_espn),
      "historical_matches":identities,
      "unmatched_espn_events":reject,
      "prospective_cross_provider_fixture_identity_certified":False,
      "source_feature_parity_certified":False,
      "scientific_oos_certified":False,
      "production_p_matrix_authorized":False,
      "telegram_signal_authorized":False,
      "automatic_wagering":False,
      "real_money":"BLOCKED"}

def capture(*,opener=urlopen,now=None):
    req=Request(URL,headers={"Accept":"application/json","User-Agent":"MATRIX-Research/1.0"})
    with opener(req,timeout=25) as response:
        if int(response.status)!=200:raise ValueError("ESPN_HTTP_NON_200")
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError("ESPN_BODY_TOO_LARGE")
    received=now or datetime.now(timezone.utc)
    return raw,received.astimezone(timezone.utc).isoformat()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,default=ARCHIVE)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--raw-out",type=Path,required=True)
    a=p.parse_args()
    if set(a.out.parts)&{"telegram","notifications","daily_prematch_reports","governance"}:
        raise SystemExit("NO_PRODUCTION_OUTPUT")
    raw,received=capture()
    source=a.archive.read_bytes()
    data=compare(source,raw,received)
    a.raw_out.parent.mkdir(parents=True,exist_ok=True)
    a.raw_out.write_bytes(raw)
    if hashlib.sha256(a.raw_out.read_bytes()).hexdigest()!=data["espn_response_sha256"]:
        raise SystemExit("ESPN_RAW_HASH_PERSIST_FAILED")
    data["espn_raw_archive_path"]=a.raw_out.as_posix()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"authentic_historic_pairs":data["exact_historical_fixture_pairs"],
                      "team_id_mappings":data["distinct_original_team_ids_crosswalked"],
                      "telegram":False},sort_keys=True))
if __name__=="__main__":main()
