"""Capture public visible tennis profile birthdates in authorized Windows CDP.

Research only. Never call SofaScore APIs, bypass HTTP limits, manufacture a
birthdate, certify provider IDs or insert a governed holdout observation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.parse import urlparse
from tools.matrix_tennis_browser_challenger_pit_gate import (
    AUTHORITIES, COUNTRY_IOC, normal, resolve_unique_precut_history,
)

BASE = Path("evidence/tennis_calendar_physical")
MONTH = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,
         "junio":6,"julio":7,"agosto":8,"septiembre":9,
         "octubre":10,"noviembre":11,"diciembre":12}
BIRTH = re.compile(
    r"(?<!\d)(\d{1,2})\s+de\s+("+ "|".join(MONTH)+r")\s+de\s+(19\d{2}|20\d{2})(?!\d)",
    re.IGNORECASE,
)

def get_sha_json(path:Path):
    raw=path.read_bytes()
    if len(raw)>7_000_000: raise ValueError("PROFILE_SOURCE_OVERSIZE")
    return json.loads(raw),hashlib.sha256(raw).hexdigest()

def birthdate_from_visible_text(text):
    """Unique source-visible Spanish DOB; never infer from names or old data."""
    values={}
    for m in BIRTH.finditer(text or ""):
        try:
            d=date(int(m.group(3)),MONTH[m.group(2).lower()],int(m.group(1)))
        except ValueError:
            continue
        values[d.strftime("%Y%m%d")]=m.group(0)
    if len(values)!=1:
        return None, "VISIBLE_BIRTHDATE_ABSENT_OR_AMBIGUOUS"
    return next(iter(values.items())), "VISIBLE_BIRTHDATE_EXACT"

def original_biography_match(player, birth, records):
    name,country=player["name"],player["country"]
    ioc=COUNTRY_IOC.get(country)
    if not ioc:return {"status":"IOC_COUNTRY_NOT_IN_ORIGINAL_RULES"}
    relevant=[r for r in records if normal(r.get("provider_display_name") or "")==normal(name)]
    selected,hreason=resolve_unique_precut_history(relevant)
    if selected is None:return {"status":hreason}
    hist=selected["pre_cut_history"]
    candidates=set()
    for r in relevant:
        for b in r.get("biographical_candidates") or []:
            if (normal(b.get("name") or "")==normal(name)
                and b.get("ioc")==ioc and b.get("dob")):
                candidates.add(str(b["dob"]))
    if not candidates:return {"status":"ORIGINAL_DOB_MISSING"}
    if len(candidates)!=1:return {"status":"ORIGINAL_DOB_CONFLICT"}
    if next(iter(candidates))!=birth:return {"status":"VISIBLE_DOB_CONFLICTS_WITH_ORIGINAL"}
    return {
        "status":"PRE_CUT_NAME_COUNTRY_BIRTHDATE_HISTORY_MATCH_RESEARCH_ONLY",
        "pre_cut_source_id":hist["canonical_source_ids"][0],
        "pre_cut_rows":hist["rows"],
        "pre_cut_latest_row_date":hist["latest_row_date"],
        "native_provider_id_mapping_certified":False,
        "production_feature_equivalence_certified":False,
    }

def valid_profile(player):
    u=urlparse(str(player.get("profile_url") or ""))
    pid=str(player.get("sofascore_player_id") or "")
    return (u.scheme=="https" and u.hostname in ("www.sofascore.com","sofascore.com")
            and u.path.startswith("/es/tennis/player/") and u.path.endswith("/"+pid)
            and pid.isdigit() and bool(player.get("name")))

def capture(root:Path, target_day:str, endpoint:str, max_profiles:int=12):
    from playwright.sync_api import Error,sync_playwright
    date.fromisoformat(target_day)
    detail_path=root/BASE/target_day/"sofascore_verified_match_details.json"
    details,detailsha=get_sha_json(detail_path)
    if (details.get("schema")!="MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1"
        or details.get("target_date_bogota")!=target_day
        or details.get("real_money")!="BLOCKED"
        or details.get("telegram_signal_authorized") is not False
        or details.get("new_model_observations_admitted")!=0):
        raise ValueError("PROFILE_DETAIL_SOURCE_NOT_GOVERNED")
    authority={}
    digests={}
    for lane,path in AUTHORITIES.items():
        doc,digest=get_sha_json(root/Path(path))
        if (doc.get("real_money")!="BLOCKED" or
            doc.get("outcomes_used") is not False or
            doc.get("post_cut_competitive_data_used") is not False or
            doc.get("silent_imputation") is not False):
            raise ValueError("PRE_CUT_AUTHORITY_UNTRUSTED")
        authority[lane]=doc.get("records") or []
        digests[lane]=digest
    candidates={}
    for event in details.get("events") or []:
        lane=event.get("surface")
        if lane not in ("Hard","Clay"):continue
        kickoff=datetime.fromisoformat(event["kickoff_utc"].replace("Z","+00:00"))
        for player in event.get("players") or []:
            if not valid_profile(player):
                continue
            pid=str(player["sofascore_player_id"])
            identity=(player["name"],player["country"],player["profile_url"],lane)
            previous=candidates.get(pid)
            if previous and previous["identity"]!=identity:
                raise ValueError("NATIVE_PROFILE_ID_SHARED_BY_CONFLICTING_PLAYERS")
            candidates[pid]={"identity":identity,"player":player,"surface":lane,
                             "kickoff_utc":kickoff}
    if not 1<=max_profiles<=24:raise ValueError("PROFILE_CAPTURE_LIMIT_INVALID")
    rows=[]
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(endpoint,timeout=20000)
        if not browser.contexts:raise ValueError("AUTHORIZED_BROWSER_CONTEXT_MISSING")
        for pid in list(sorted(candidates))[:max_profiles]:
            source=candidates[pid]
            player=source["player"]
            page=browser.contexts[0].new_page()
            record={"name":player["name"],"country":player["country"],
                    "sofascore_player_id":pid,"profile_url":player["profile_url"],
                    "surface":source["surface"],
                    "kickoff_utc":source["kickoff_utc"].isoformat(),
                    "approved_model_player_id":False}
            try:
                response=page.goto(player["profile_url"],wait_until="domcontentloaded",timeout=16000)
                if response and response.status in (401,403,429):
                    record["status"]="PROVIDER_RESTRICTED_"+str(response.status)
                    rows.append(record);continue
                page.wait_for_timeout(900)
                visible=page.evaluate("() => ({url:location.href,text:String(document.body?.innerText||'').slice(0,60000)})")
                raw=str(visible.get("text") or "")
                record["observed_at_utc"]=datetime.now(timezone.utc).isoformat()
                record["visible_page_sha256"]=hashlib.sha256(
                    json.dumps(visible,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest()
                if urlparse(str(visible.get("url") or "")).path!=urlparse(player["profile_url"]).path:
                    record["status"]="PROFILE_REDIRECT_IDENTITY_MISMATCH"
                else:
                    birth,why=birthdate_from_visible_text(raw)
                    record["status"]=why
                    if birth:
                        record["visible_birth_date_text"]=birth[1]
                        record["visible_birth_date_yyyymmdd"]=birth[0]
                        observed=datetime.fromisoformat(record["observed_at_utc"])
                        record["observed_before_kickoff"]=observed<source["kickoff_utc"]
                        research=original_biography_match(player,birth[0],authority[source["surface"]])
                        record["original_match_research"]=research
                        if not record["observed_before_kickoff"]:
                            record["status"]="AFTER_KICKOFF_RESEARCH_ONLY"
            except (Error,ValueError,KeyError,TypeError,OSError) as e:
                record["status"]=str(e) if isinstance(e,ValueError) else type(e).__name__
            finally:
                page.close()
            rows.append(record)
    report={
        "schema":"MATRIX_TENNIS_FREE_VISIBLE_PROFILE_BIRTHDATES_RESEARCH_V1",
        "target_date_bogota":target_day,
        "captured_at_utc":datetime.now(timezone.utc).isoformat(),
        "method":"USER_AUTHORIZED_CDP_VISIBLE_PROFILE_PAGES",
        "source_detail_sha256":detailsha,
        "original_pre_cut_authority_sha256":digests,
        "profiles_requested":min(len(candidates),max_profiles),
        "profiles":rows,
        "exact_pre_cut_biography_research_count":sum(
            r.get("status")=="VISIBLE_BIRTHDATE_EXACT" and
            (r.get("original_match_research") or {}).get("status")==
            "PRE_CUT_NAME_COUNTRY_BIRTHDATE_HISTORY_MATCH_RESEARCH_ONLY"
            and r.get("observed_before_kickoff") is True for r in rows),
        "provider_identity_equivalence_certified":False,
        "current_ranking_or_pit_features_certified":False,
        "official_holdout_admitted":0,"model_parameters_modified":False,
        "telegram_signal_authorized":False,"automatic_wagering":False,
        "paid_api_used":False,"real_money":"BLOCKED",
    }
    output=root/BASE/target_day/"MATRIX_TENNIS_FREE_VISIBLE_PROFILE_BIRTHDATES_RESEARCH.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in (
        "target_date_bogota","profiles_requested",
        "exact_pre_cut_biography_research_count","official_holdout_admitted",
        "real_money")},sort_keys=True))
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path.cwd())
    parser.add_argument("--date",required=True)
    parser.add_argument("--endpoint",default="http://127.0.0.1:9222")
    parser.add_argument("--max-profiles",type=int,default=12)
    a=parser.parse_args()
    capture(a.root,a.date,a.endpoint,a.max_profiles)

if __name__=="__main__":main()
