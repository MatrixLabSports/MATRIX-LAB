"""Read-only football fixture crosscheck: Flashscore versus SofaScore and provider.

No prices are inferred from either calendar. No Telegram or betting activation.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

BOGOTA=ZoneInfo("America/Bogota")
# Explicit source-name reconciliation for observed league/team aliases;
# unknown aliases never become fuzzy cross-provider matches.
ALIASES={
    # Individually corroborated 2026-11-03 provider/browser names; no fuzzy promotion.
    # Independently observed 04-Nov-2026 exact source-to-Flash names.
    "fenerbahce sk":"fenerbahce",
    "liverpool fc":"liverpool",
    "portsmouth fc":"portsmouth",
    "swansea city afc":"swansea",
    "derby county fc":"derby",
    "norwich city fc":"norwich",
    "blackburn rovers fc":"blackburn",
    "stoke city fc":"stoke",
    "watford fc":"watford",
    "lincoln city fc":"lincoln",
    "charlton athletic fc":"charlton",
    "bolton wanderers fc":"bolton",
    "birmingham city fc":"birmingham",
    "millwall fc":"millwall",
    "chapecoense af":"chapecoense",
    "mirassol fc":"mirassol",
    "us sassuolo calcio":"sassuolo",
    "acf fiorentina":"fiorentina",
    "atalanta bc":"atalanta",
    "parma calcio 1913":"parma",
    "fc lorient":"lorient",
    "stade brestois 29":"brest",
    "newcastle united fc":"newcastle",
    "everton fc":"everton",
    "rc deportivo la coruna":"deportivo de a coruna",
    "ca osasuna":"osasuna",
    "sport lisboa e benfica":"benfica",
    "fc alverca":"alverca",
    "gil vicente fc":"gil vicente",
    "vitoria sc":"vitoria guimaraes",
    "rb bragantino":"bragantino",
    "santos fc":"santos",
}

def norm(value):
    s=unicodedata.normalize("NFKD",str(value or "")).casefold()
    s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+"," ",s).strip()

def check(intake:dict,sofa:dict,observation:dict|None)->dict:
    result={"schema":"MATRIX_FLASH_FOOTBALL_CROSSCHECK_V1",
      "target_date_bogota":intake.get("target_date_bogota"),
      "source_order":["SOFASCORE","FLASHSCORE","APIS"],
      "status":"BLOCKED_MISSING_FLASH_BROWSER_EVIDENCE",
      "matched":[],"rejected":[],"matched_count":0,"rejected_count":0,
      "sofascore_verified":False,"flashscore_verified":False,
      "odds_market_verified":False,"calibration_parity_verified":False,
      "signal_generation_authorized":False,"automatic_wagering":False,"real_money":"BLOCKED"}
    if observation is None:
        return result
    if (intake.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or sofa.get("schema")!="MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK_V1"
        or observation.get("schema")!="MATRIX_FLASH_BROWSER_OBSERVATIONS_V1"):
        raise ValueError("UNTRUSTED_CALENDAR_SCHEMA")
    day=intake.get("target_date_bogota")
    if day!=sofa.get("target_date_bogota") or day!=observation.get("target_date_bogota"):
        raise ValueError("CALENDAR_TARGET_DATE_MISMATCH")
    if any(x.get("real_money")!="BLOCKED" for x in (intake,sofa,observation)):
        raise ValueError("REAL_MONEY_GOVERNANCE_VIOLATION")
    if sofa.get("status")!="PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL" or sofa.get("rejected_count")!=0:
        return result
    if observation.get("source")!="FLASHSCORE" or observation.get("automatic_wagering") is not False:
        raise ValueError("FLASH_SOURCE_OR_AUTOWAGER_UNTRUSTED")
    observed=datetime.fromisoformat(observation["observed_at_utc"].replace("Z","+00:00"))
    if observed.utcoffset() is None:
        raise ValueError("OBSERVATION_TIMEZONE_REQUIRED")
    observed=observed.astimezone(timezone.utc)
    sources={str(f.get("source_fixture_id")):f for f in intake.get("fixtures",[]) if isinstance(f,dict)}
    prior={str(f.get("fixture_id")):f for f in sofa.get("matched",[]) if isinstance(f,dict)}
    seen_fixtures=set();seen_mid=set()
    for obs in observation.get("matches",[]):
        if not isinstance(obs,dict):continue
        fid=str(obs.get("provider_fixture_id") or "")
        mid=str(obs.get("flashscore_mid") or "")
        if fid in seen_fixtures or mid in seen_mid or not fid or not mid:
            raise ValueError("DUPLICATE_OR_MISSING_PROVIDER_ID")
        seen_fixtures.add(fid);seen_mid.add(mid)
        item={"source_fixture_id":fid,"flashscore_mid":mid}
        source=sources.get(fid)
        reason=None
        if not source or fid not in prior:
            reason="MISSING_INDEPENDENT_OR_SOFA_PREREGISTRATION"
        else:
            try:
                kickoff=datetime.fromisoformat(source["kickoff_utc"].replace("Z","+00:00"))
                if kickoff.utcoffset() is None:raise ValueError("KICKOFF_TZ_MISSING")
                kickoff=kickoff.astimezone(timezone.utc)
                if kickoff.isoformat()!=prior[fid]["kickoff_utc"]:
                    reason="SOFA_KICKOFF_CONTRADICTION"
                elif kickoff<=observed:
                    reason="OBSERVATION_AFTER_KICKOFF"
                elif kickoff.astimezone(BOGOTA).date().isoformat()!=day or kickoff.astimezone(BOGOTA).strftime("%H:%M")!=obs.get("local_time_bogota"):
                    reason="FLASH_KICKOFF_CONTRADICTION"
            except (ValueError,KeyError,TypeError):
                reason="INVALID_KICKOFF"
            if reason is None:
                label=str(obs.get("match") or "")
                parts=label.split(" - ")
                if (len(parts)!=2 or
                    norm(parts[0])!=ALIASES.get(norm(source["home"]),norm(source["home"])) or
                    norm(parts[1])!=ALIASES.get(norm(source["away"]),norm(source["away"]))):
                    reason="FLASH_TEAM_ORIENTATION_CONTRADICTION"
            if reason is None:
                url=str(obs.get("url") or "")
                parsed=urlparse(url)
                query=parse_qs(parsed.query)
                if (parsed.scheme!="https" or parsed.netloc!="www.flashscore.co"
                    or not parsed.path.startswith("/partido/futbol/")
                    or query.get("mid") != [mid] or not re.fullmatch(r"[A-Za-z0-9]{8}",mid)):
                    reason="FLASH_EVENT_URL_IDENTITY_INVALID"
        if reason:
            result["rejected"].append({**item,"reason":reason})
        else:
            result["matched"].append({**item,"sofascore_event_id":prior[fid]["sofascore_event_id"],
                                       "kickoff_utc":source["kickoff_utc"],"flashscore_url":obs["url"],
                                       "three_source_calendar_identity_verified":True})
    result["matched_count"]=len(result["matched"])
    result["rejected_count"]=len(result["rejected"])
    result["sofascore_verified"]=result["matched_count"]>0
    result["flashscore_verified"]=result["matched_count"]>0 and not result["rejected"]
    if result["flashscore_verified"]:
        result["status"]="PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS"
    else:
        result["status"]="BLOCKED_FLASH_IDENTITY_OR_KICKOFF_MISMATCH"
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--intake",type=Path,required=True)
    p.add_argument("--sofa",type=Path,required=True)
    p.add_argument("--flash-observations",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    load=lambda path:json.loads(path.read_text(encoding="utf-8"))
    result=check(load(a.intake),load(a.sofa),load(a.flash_observations) if a.flash_observations.is_file() else None)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","matched_count","rejected_count","flashscore_verified","signal_generation_authorized")},sort_keys=True))

if __name__=="__main__":
    main()
