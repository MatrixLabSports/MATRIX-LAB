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

LANE_BET_IDS={
    "CORNERS_OVER_UNDER":{45,57,58,77,127,132,133,134,135},
    "CARDS_OVER_UNDER":{80,82,83,335},
    "PLAYER_SHOTS":{240,241,265,270,276},
    "PLAYER_SHOTS_ON_TARGET":{242,264,269,275},
    "GOALKEEPER_SAVES":{267,268,274,315,318,319},
    "PLAYER_ASSISTS":{212,255,256},
    "PLAYER_PASSES":{273,279},
    "PLAYER_TACKLES":{272,278},
    "PLAYER_FOULS":{266,271,277},
    "TEAM_SHOTS_ON_TARGET":{87,88,89,243,244},
}


def run(api_key:str,fixture_ids:list[str],out_dir:Path,session:Any|None=None)->dict[str,Any]:
    key=str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    if not fixture_ids:
        raise ValueError("FIXTURE_IDS_REQUIRED")
    out_dir.mkdir(parents=True,exist_ok=True)
    client=session or requests.Session()
    lane_seen={k:{"fixtures":[],"bookmakers":set(),"bets":{}} for k in LANE_BET_IDS}
    captures=[]

    for fid in fixture_ids:
        response=client.get(
            BASE_URL+"/odds",
            headers={"x-apisports-key":key},
            params={"fixture":fid},
            timeout=TIMEOUT_SECONDS,
        )
        body=bytes(response.content)
        (out_dir/f"fixture_{fid}_odds.bin").write_bytes(body)
        payload=response.json()
        errors=payload.get("errors") if isinstance(payload,Mapping) else None
        rows=payload.get("response") if isinstance(payload,Mapping) else None
        valid_rows=[x for x in rows if isinstance(x,Mapping)] if isinstance(rows,list) else []
        bookmaker_names=set()
        observed_bets={}
        for row in valid_rows:
            for book in row.get("bookmakers") or []:
                if not isinstance(book,Mapping): continue
                book_name=str(book.get("name") or "").strip()
                if book_name: bookmaker_names.add(book_name)
                for bet in book.get("bets") or []:
                    if not isinstance(bet,Mapping): continue
                    try: bid=int(bet.get("id"))
                    except (TypeError,ValueError): continue
                    bname=str(bet.get("name") or "").strip()
                    observed_bets[bid]=bname
                    for lane,ids in LANE_BET_IDS.items():
                        if bid in ids:
                            if fid not in lane_seen[lane]["fixtures"]:
                                lane_seen[lane]["fixtures"].append(fid)
                            if book_name:
                                lane_seen[lane]["bookmakers"].add(book_name)
                            lane_seen[lane]["bets"][str(bid)]=bname
        captures.append({
            "fixture_id":fid,
            "http_status":int(response.status_code),
            "provider_errors":errors,
            "provider_rows":len(valid_rows),
            "bookmaker_count":len(bookmaker_names),
            "bookmakers":sorted(bookmaker_names),
            "observed_bet_count":len(observed_bets),
            "observed_bets":{str(k):v for k,v in sorted(observed_bets.items())},
            "raw_sha256":hashlib.sha256(body).hexdigest(),
        })

    lanes={}
    for lane,seen in lane_seen.items():
        lanes[lane]={
            "fixture_count_with_market":len(seen["fixtures"]),
            "fixtures":seen["fixtures"],
            "bookmaker_count":len(seen["bookmakers"]),
            "bookmakers":sorted(seen["bookmakers"]),
            "observed_bets":seen["bets"],
            "live_prematch_price_status":"VERIFIED_PRESENT" if seen["fixtures"] else "NOT_OBSERVED_IN_PROBED_FIXTURES",
        }

    manifest={
        "schema":"MATRIX_API_FOOTBALL_EXTENDED_FIXTURE_ODDS_PROBE_V1",
        "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider":"api_football",
        "endpoint":"/odds",
        "fixture_ids":fixture_ids,
        "network_calls":len(fixture_ids),
        "captures":captures,
        "lanes":lanes,
        "scope_note":"Prematch price availability is fixture/bookmaker specific; absence in this sample is not proof of global absence.",
        "odds_used_to_generate_model_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    (out_dir/"manifest.json").write_text(
        json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
        encoding="utf-8",
    )
    return manifest


def main()->None:
    raw=os.environ.get("MATRIX_API_FOOTBALL_ODDS_FIXTURE_IDS","").strip()
    ids=[x.strip() for x in raw.split(",") if x.strip()]
    r=run(
        os.environ.get("API_FOOTBALL_KEY",""),
        ids,
        Path("evidence/api_football/market_expansion/fixture_odds_probe"),
    )
    print(json.dumps({
        "status":r["status"],
        "fixture_ids":r["fixture_ids"],
        "lane_status":{k:v["live_prematch_price_status"] for k,v in r["lanes"].items()},
        "real_money":r["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
