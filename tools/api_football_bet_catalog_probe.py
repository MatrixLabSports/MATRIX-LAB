from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL="https://v3.football.api-sports.io"
ENDPOINT="/odds/bets"
TIMEOUT_SECONDS=20.0


def run(api_key:str,out_dir:Path,session:Any|None=None)->dict[str,Any]:
    key=str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    out_dir.mkdir(parents=True,exist_ok=True)
    client=session or requests.Session()
    started=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    response=client.get(
        BASE_URL+ENDPOINT,
        headers={"x-apisports-key":key},
        timeout=TIMEOUT_SECONDS,
    )
    body=bytes(response.content)
    (out_dir/"bets.bin").write_bytes(body)
    payload=response.json()
    errors=payload.get("errors") if isinstance(payload,Mapping) else None
    rows=payload.get("response") if isinstance(payload,Mapping) else None
    valid=[x for x in rows if isinstance(x,Mapping)] if isinstance(rows,list) else []
    catalog=[]
    for row in valid:
        catalog.append({
            "id":row.get("id"),
            "name":str(row.get("name") or "").strip(),
        })
    names=[x["name"] for x in catalog if x["name"]]
    folded=[x.casefold() for x in names]
    keywords={
        "corners":["corner"],
        "cards":["card","booking"],
        "shots":["shot"],
        "shots_on_target":["shot on target","shots on target"],
        "saves":["save"],
        "assists":["assist"],
        "passes":["pass"],
        "tackles":["tackle"],
        "fouls":["foul"],
    }
    matches={}
    for market,terms in keywords.items():
        matches[market]=[
            catalog[i] for i,name in enumerate(folded)
            if any(term in name for term in terms)
        ]
    provider_error=errors not in ({},[],None)
    ok=200 <= int(response.status_code) < 300 and not provider_error and isinstance(rows,list)
    manifest={
        "schema":"MATRIX_API_FOOTBALL_BET_CATALOG_PROBE_V1",
        "provider":"api_football",
        "endpoint":ENDPOINT,
        "request_started_at_utc":started,
        "response_observed_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "http_status":int(response.status_code),
        "provider_errors":errors,
        "provider_rows":len(valid),
        "bets":catalog,
        "extended_market_matches":matches,
        "network_calls_performed":1,
        "raw_sha256":hashlib.sha256(body).hexdigest(),
        "raw_bytes":len(body),
        "automatic_wagering":False,
        "odds_used_to_generate_model_probability":False,
        "real_money":"BLOCKED",
        "status":"PASS" if ok else "BLOCKED",
    }
    (out_dir/"manifest.json").write_text(
        json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
        encoding="utf-8"
    )
    return manifest


def main()->None:
    r=run(
        os.environ.get("API_FOOTBALL_KEY",""),
        Path("evidence/api_football/market_expansion/bet_catalog"),
    )
    print(json.dumps({
        "status":r["status"],
        "provider_rows":r["provider_rows"],
        "extended_market_match_counts":{k:len(v) for k,v in r["extended_market_matches"].items()},
        "real_money":r["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
