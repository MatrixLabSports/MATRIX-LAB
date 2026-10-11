from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT_SECONDS=20.0
MAX_CALLS=30

TARGETS={
    "PLAYER_PASSES":{273,279},
    "PLAYER_TACKLES":{272,278},
    "PLAYER_FOULS":{266,271,277},
}

PRIORITY_TERMS=(
    "Serie B","Liga MX","USL Championship","Primera A","Major League Soccer",
    "UEFA","Premier League","Championship","Copa","Division Profesional"
)


def _utc(v:object)->datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    return dt.astimezone(timezone.utc)


def _candidates(freeze:Mapping[str,Any],now:datetime)->list[dict[str,Any]]:
    rows=[r for r in freeze.get("rows",[]) if isinstance(r,Mapping)]
    future=[r for r in rows if _utc(r.get("kickoff_utc"))>now]
    def key(r):
        comp=str(r.get("competition_name") or "")
        priority=0 if any(t.casefold() in comp.casefold() for t in PRIORITY_TERMS) else 1
        return (priority,str(r.get("kickoff_utc") or ""),str(r.get("fixture_id") or ""))
    future.sort(key=key)
    return [dict(r) for r in future]


def run(api_key:str,freeze_path:Path,out_dir:Path,session:Any|None=None,max_calls:int=MAX_CALLS)->dict[str,Any]:
    key=str(api_key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    freeze=json.loads(freeze_path.read_text(encoding="utf-8"))
    now=datetime.now(timezone.utc).replace(microsecond=0)
    candidates=_candidates(freeze,now)
    client=session or requests.Session()
    out_dir.mkdir(parents=True,exist_ok=True)
    found={k:{"fixtures":[],"bookmakers":set(),"bets":{}} for k in TARGETS}
    scans=[]

    for row in candidates:
        if len(scans)>=max_calls: break
        if all(found[k]["fixtures"] for k in TARGETS): break
        fid=str(row.get("fixture_id"))
        response=client.get(
            BASE_URL+"/odds",
            headers={"x-apisports-key":key},
            params={"fixture":fid},
            timeout=TIMEOUT_SECONDS,
        )
        body=bytes(response.content)
        payload=response.json()
        errors=payload.get("errors") if isinstance(payload,Mapping) else None
        entries=payload.get("response") if isinstance(payload,Mapping) else None
        entries=[x for x in entries if isinstance(x,Mapping)] if isinstance(entries,list) else []
        observed={}
        bookmaker_names=set()
        for entry in entries:
            for book in entry.get("bookmakers") or []:
                if not isinstance(book,Mapping): continue
                bname=str(book.get("name") or "").strip()
                if bname: bookmaker_names.add(bname)
                for bet in book.get("bets") or []:
                    if not isinstance(bet,Mapping): continue
                    try: bid=int(bet.get("id"))
                    except (TypeError,ValueError): continue
                    name=str(bet.get("name") or "").strip()
                    observed[bid]=name
                    for lane,ids in TARGETS.items():
                        if bid in ids:
                            if fid not in found[lane]["fixtures"]: found[lane]["fixtures"].append(fid)
                            if bname: found[lane]["bookmakers"].add(bname)
                            found[lane]["bets"][str(bid)]=name
        scans.append({
            "fixture_id":fid,
            "competition":row.get("competition_name"),
            "home":row.get("home_team_name"),
            "away":row.get("away_team_name"),
            "kickoff_utc":row.get("kickoff_utc"),
            "http_status":int(response.status_code),
            "provider_errors":errors,
            "provider_rows":len(entries),
            "bookmaker_count":len(bookmaker_names),
            "raw_sha256":hashlib.sha256(body).hexdigest(),
        })

    result={}
    for lane,data in found.items():
        result[lane]={
            "status":"LIVE_PREMATCH_PRICE_VERIFIED" if data["fixtures"] else "CATALOG_VERIFIED_BUT_NOT_LIVE_OBSERVED",
            "fixtures":data["fixtures"],
            "bookmakers":sorted(data["bookmakers"]),
            "observed_bets":data["bets"],
        }
    manifest={
        "schema":"MATRIX_API_FOOTBALL_EXTENDED_ODDS_GAP_SCANNER_V1",
        "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider":"api_football",
        "endpoint":"/odds",
        "max_calls_policy":max_calls,
        "network_calls":len(scans),
        "scans":scans,
        "targets":result,
        "scope_note":"Bounded discovery; non-observation does not prove global market absence.",
        "odds_used_to_generate_model_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    (out_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest


def main()->None:
    r=run(
        os.environ.get("API_FOOTBALL_KEY",""),
        Path("evidence/api_football/prospective_market_freeze/freeze.json"),
        Path("evidence/api_football/market_expansion/odds_gap_scan"),
        max_calls=int(os.environ.get("MATRIX_EXTENDED_ODDS_GAP_MAX_CALLS","30")),
    )
    print(json.dumps({
        "status":r["status"],
        "network_calls":r["network_calls"],
        "targets":{k:v["status"] for k,v in r["targets"].items()},
        "real_money":r["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
