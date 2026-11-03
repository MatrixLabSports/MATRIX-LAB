"""Verify physically observed SofaScore fixture identities against independent fixtures.

Manual browser observations do not establish market quotes, full world coverage
or permission to promote an independently sourced model. No network or Telegram.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BOGOTA=ZoneInfo("America/Bogota")
ALIASES={
    # Individually corroborated 2026-11-03 provider/browser names; no fuzzy promotion.
    "portsmouth fc":"portsmouth",
    "swansea city afc":"swansea city",
    "derby county fc":"derby county",
    "norwich city fc":"norwich city",
    "blackburn rovers fc":"blackburn rovers",
    "stoke city fc":"stoke city",
    "watford fc":"watford",
    "lincoln city fc":"lincoln city",
    "charlton athletic fc":"charlton athletic",
    "bolton wanderers fc":"bolton wanderers",
    "birmingham city fc":"birmingham city",
    "millwall fc":"millwall",
    "chapecoense af":"chapecoense",
    "mirassol fc":"mirassol",
    "us sassuolo calcio":"sassuolo",
    "acf fiorentina":"fiorentina",
    "atalanta bc":"atalanta",
    "parma calcio 1913":"parma",
    "fc lorient":"lorient",
    "stade brestois 29":"stade brestois",
    "newcastle united fc":"newcastle united",
    "everton fc":"everton",
    "rc deportivo la coruna":"deportivo de a coruna",
    "ca osasuna":"osasuna",
    "sport lisboa e benfica":"benfica",
    "fc alverca":"fc alverca",
    "gil vicente fc":"gil vicente",
    "vitoria sc":"vitoria sc",
    "rb bragantino":"rb bragantino",
    "santos fc":"santos",
}

def norm(text):
    s=unicodedata.normalize("NFKD",str(text or ""))
    s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+"," ",s.casefold()).strip()

def corroborate(intake,obs):
    result={
        "schema":"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK_V1",
        "source_order":["SOFASCORE","FLASHSCORE","APIS"],
        "status":"BLOCKED_BROWSER_EVIDENCE",
        "target_date_bogota":intake.get("target_date_bogota"),
        "matched_count":0,"matched":[],"rejected":[],
        "sofascore_observed":False,"flashscore_verified":False,
        "historical_source_equivalence_verified":False,
        "governed_model_parity_verified":False,
        "over25_exact_quote_verified":False,
        "signal_generation_authorized":False,"automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    if obs is None:
        result["status"]="BLOCKED_NO_CURRENT_BROWSER_CAPTURE"
        return result
    if intake.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1" or obs.get("schema")!="MATRIX_SOFA_BROWSER_OBSERVATIONS_V1":
        raise ValueError("UNTRUSTED_BROWSER_OR_FIXTURE_SCHEMA")
    if obs.get("source")!="SOFASCORE" or obs.get("real_money")!="BLOCKED" or intake.get("real_money")!="BLOCKED":
        raise ValueError("UNTRUSTED_SOURCE_OR_MONEY_SCOPE")
    if intake.get("target_date_bogota")!=obs.get("target_date_bogota"):
        raise ValueError("BROWSER_CAPTURE_TARGET_DATE_MISMATCH")
    observed=datetime.fromisoformat(obs["observed_at_utc"].replace("Z","+00:00"))
    if observed.tzinfo is None:
        raise ValueError("BROWSER_CAPTURE_UNAWARE_TIMESTAMP")
    observed=observed.astimezone(timezone.utc)
    rows={str(x.get("source_fixture_id")):x for x in intake.get("fixtures") or [] if isinstance(x,dict)}
    seen_source=set(); seen_browser=set()
    for o in obs.get("matches") or []:
        if not isinstance(o,dict):
            continue
        fid=str(o.get("provider_fixture_id") or "")
        sid=str(o.get("sofascore_event_id") or "")
        if fid in seen_source or sid in seen_browser:
            raise ValueError("DUPLICATE_CROSS_PROVIDER_FIXTURE_IDENTITY")
        seen_source.add(fid);seen_browser.add(sid)
        source=rows.get(fid)
        reason=None
        if not source:
            reason="UNMATCHED_INDEPENDENT_FIXTURE_ID"
        else:
            try:
                kickoff=datetime.fromisoformat(source["kickoff_utc"].replace("Z","+00:00"))
                if kickoff.tzinfo is None:raise ValueError("UNAWARE_KICKOFF")
                kickoff=kickoff.astimezone(timezone.utc)
                match_date=kickoff.astimezone(BOGOTA).date().isoformat()
                clock=kickoff.astimezone(BOGOTA).strftime("%H:%M")
            except (ValueError,TypeError,KeyError):
                reason="INVALID_INDEPENDENT_KICKOFF"
            if not reason and (match_date!=obs["target_date_bogota"] or clock!=o.get("local_time_bogota")):
                reason="BROWSER_TIME_MISMATCH"
            if not reason and observed>=kickoff:
                reason="BROWSER_OBSERVATION_NOT_PROSPECTIVE"
            if not reason and (
                ALIASES.get(norm(source.get("home")),norm(source.get("home")))!=norm(o.get("home")) or
                ALIASES.get(norm(source.get("away")),norm(source.get("away")))!=norm(o.get("away"))
            ):
                reason="BROWSER_TEAM_IDENTITY_MISMATCH"
            if not reason and (
                not sid.isdigit() or
                not str(o.get("url") or "").startswith("https://www.sofascore.com/es/football/match/") or
                not str(o.get("url") or "").endswith("#id:"+sid)
            ):
                reason="BROWSER_PROVIDER_EVENT_URL_MISMATCH"
        if reason:
            result["rejected"].append({"fixture_id":fid,"sofascore_event_id":sid,"reason":reason})
        else:
            result["matched"].append({"fixture_id":fid,"sofascore_event_id":sid,
                                      "kickoff_utc":source["kickoff_utc"],
                                      "sofascore_url":o["url"],
                                      "identity_time_and_teams_verified":True})
    result["matched_count"]=len(result["matched"])
    result["rejected_count"]=len(result["rejected"])
    result["sofascore_observed"]=len(result["matched"])>0
    result["status"]="PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL" if result["matched_count"] and not result["rejected"] else "BLOCKED_BROWSER_MISMATCH"
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--intake",required=True,type=Path)
    p.add_argument("--observations",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    read=lambda x:json.loads(x.read_text(encoding="utf-8"))
    r=corroborate(read(a.intake),read(a.observations) if a.observations.is_file() else None)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":r["status"],"matched_count":r["matched_count"],
                      "rejected_count":r.get("rejected_count",0),"signal_generation_authorized":False},sort_keys=True))
if __name__=="__main__":main()
