"""Bounded post-subscription original API-Football FREE entitlement probe.

This is the only direct way to retain original API-Football league/team IDs
without a new provider crosswalk if the key still has authorized free access.
Do not assume entitlement from HTTP 200. Never sends a bet or signal.
"""
from __future__ import annotations
import argparse,hashlib,json,os,time
from datetime import datetime,timezone
from pathlib import Path
import requests

BASE="https://v3.football.api-sports.io"
LEAGUES=("39","61","78","135","140","239")
OUT=Path("evidence/api_football/free_fallback")
HEADERS=("x-ratelimit-requests-limit","x-ratelimit-requests-remaining","x-ratelimit-limit","x-ratelimit-remaining")
MAX_CALLS=7

def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def probe(*,key:str,now:datetime,root:Path,session=None)->dict:
    day=now.astimezone(timezone.utc).date().isoformat()
    directory=root/OUT/day
    directory.mkdir(parents=True,exist_ok=True)
    if not key:
        result={"schema":"MATRIX_ORIGINAL_API_FOOTBALL_FREE_ACCESS_PROBE_V1",
           "status":"ORIGINAL_API_FOOTBALL_KEY_MISSING",
           "calls":0,"leagues":[],"original_six_league_coverage_verified":False,
           "model_parameters_modified":False,"production_p_matrix_authorized":False,
           "telegram_signal_authorized":False,"automatic_wagering":False,
           "real_money":"BLOCKED"}
        write(directory/"manifest.json",result);return result
    if not key.isascii() or len(key)>1000:
        raise ValueError("INVALID_ORIGINAL_API_KEY_FORMAT")
    client=session or requests.Session()
    summaries=[];calls=0;remaining=None
    for league in LEAGUES:
        if calls>=6 or remaining is not None and remaining<=20:break
        url=BASE+"/fixtures"
        try:
            response=client.get(url,params={"league":league,"season":"2026","next":"1"},
                    headers={"x-apisports-key":key,"accept":"application/json"},timeout=20)
            calls+=1
        except requests.RequestException as e:
            summaries.append({"league":league,"status":"PROVIDER_NETWORK_BLOCK",
                            "exception":type(e).__name__});break
        body=bytes(response.content)
        rates={k:v for k,v in response.headers.items() if k.lower() in HEADERS}
        for k,v in rates.items():
            if k.lower()=="x-ratelimit-requests-remaining" and str(v).isdigit():
                remaining=int(v)
        if len(body)>2_000_000:
            summaries.append({"league":league,"status":"OVERSIZED_PROVIDER_RESPONSE","http_status":response.status_code})
            continue
        raw_sha=sha(body)
        path=directory/(league+"_"+raw_sha[:18]+".json")
        if path.exists():
            if path.read_bytes()!=body:raise ValueError("PROVIDER_EVIDENCE_SHA_COLLISION")
        else:
            with path.open("xb") as f:f.write(body)
        try: doc=json.loads(body)
        except (UnicodeError,ValueError,TypeError):doc={}
        errors=doc.get("errors") if isinstance(doc,dict) else None
        rows=doc.get("response") if isinstance(doc,dict) else None
        positive=(response.status_code==200 and errors in (None,{},[],False)
            and isinstance(rows,list) and len(rows)>0)
        first=rows[0] if positive else {}
        f=first.get("fixture") if isinstance(first,dict) else {}
        comp=first.get("league") if isinstance(first,dict) else {}
        league_match=str(comp.get("id"))==league if isinstance(comp,dict) else False
        fixture_ok=(isinstance(f,dict) and type(f.get("id"))==int
                    and isinstance(f.get("date"),str) and league_match)
        summaries.append({"league":league,"http_status":response.status_code,
           "provider_error_present":bool(errors),
           "provider_error_class":str(type(errors).__name__) if errors else None,
           "provider_response_rows":len(rows) if isinstance(rows,list) else None,
           "fixture_identity_and_competition_verified":bool(positive and fixture_ok),
           "original_fixture_id":f.get("id") if fixture_ok else None,
           "fixture_kickoff_utc":f.get("date") if fixture_ok else None,
           "response_sha256":raw_sha,"response_file":path.relative_to(root).as_posix(),
           "rate":rates,
           "status":"ORIGINAL_ID_FREE_ENDPOINT_PASS" if positive and fixture_ok else "ORIGINAL_ID_FREE_ENDPOINT_NOT_VERIFIED"})
        # Do not burn remaining calls if the key is rejected/expired; a 429
        # or provider error cannot be bypassed by another client identity.
        if response.status_code in (401,403,429) or errors:
            break
        if calls<len(LEAGUES):time.sleep(.35)
    covered=sum(x.get("fixture_identity_and_competition_verified") is True for x in summaries)
    result={"schema":"MATRIX_ORIGINAL_API_FOOTBALL_FREE_ACCESS_PROBE_V1",
       "checked_at_utc":now.astimezone(timezone.utc).isoformat(),
       "status":"SIX_LEAGUES_NATIVE_ORIGINAL_ID_DISCOVERY_ONLY" if covered==6 else "PARTIAL_OR_NO_AUTHORIZED_ORIGINAL_FREE_COVERAGE",
       "calls":calls,"free_or_existing_entitlement_claim":"NOT_VERIFIED_FROM_REQUEST_SUCCESS_ALONE",
       "original_league_id_coverage":covered,
       "leagues":summaries,
       "original_six_league_coverage_verified":covered==6,
       "historical_enriched_pit_inputs_verified":False,
       "original_feature_parity_reinstated":False,
       "model_parameters_modified":False,
       "production_p_matrix_authorized":False,
       "telegram_signal_authorized":False,
       "automatic_wagering":False,"real_money":"BLOCKED"}
    write(directory/"manifest.json",result)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    a=p.parse_args()
    x=probe(key=os.getenv("API_FOOTBALL_KEY","").strip(),
       now=datetime.now(timezone.utc),root=a.root)
    print(json.dumps({"status":x["status"],"network_calls":x["calls"],
        "native_original_league_id_coverage":x.get("original_league_id_coverage",0),
        "automatic_wagering":False,"real_money":"BLOCKED"},sort_keys=True))
if __name__=="__main__":main()
