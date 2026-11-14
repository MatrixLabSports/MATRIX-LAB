from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

OUT = Path("evidence/governance/MATRIX_FREE_API_AUTHENTICATED_PROBE_LAST.json")
TIMEOUT = 15

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def get_json(url: str, headers: dict[str, str],
             params: dict[str, Any] | None = None,
             session=None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Never persist or log tokens, response bodies, or sensitive URLs."""
    get=(session or requests).get
    response=get(url,headers=headers,params=params or {},timeout=TIMEOUT)
    body=bytes(response.content[:250001])
    if len(body)>250000:
        raise ValueError("PROVIDER_RESPONSE_OVERSIZE")
    meta={"http_status":int(response.status_code),
          "response_bytes":len(body),
          "response_sha256":sha256_bytes(body),
          "content_type":response.headers.get("content-type")}
    try: parsed=response.json()
    except (ValueError,TypeError): parsed={"_non_json":True}
    if not isinstance(parsed,dict):parsed={"_invalid_shape":True}
    return parsed,meta

def single_provider(provider_id:str,key:str,url:str,header:str,expected_list:str,
                    params=None,session=None)->dict:
    if not key:
        return {"status":"KEY_NOT_CONFIGURED","authenticated":False,
                "data_verified":False,"calls":0,"token_redacted":True}
    try:
        data,meta=get_json(url,{header:key},params,session)
        rows=data.get(expected_list)
        ok=meta["http_status"]==200 and isinstance(rows,list) and len(rows)>0
        reason=("HTTP_200_WITH_NONEMPTY_VERIFIED_LIST" if ok else
                "HTTP_"+str(meta["http_status"]) if meta["http_status"]!=200 else
                "EMPTY_OR_INVALID_PROVIDER_LIST")
        return {"status":reason,"authenticated":ok,
                "data_verified":ok,"calls":1,"response":meta,
                "returned_count":len(rows) if isinstance(rows,list) else None,
                "token_redacted":True}
    except (requests.RequestException,ValueError,TimeoutError) as exc:
        return {"status":"NETWORK_OR_RESPONSE_BLOCK_"+type(exc).__name__,
                "authenticated":False,"data_verified":False,"calls":1,
                "token_redacted":True}

def probe(football_key:str,tennis_key:str, *, tennis_opt_in:bool=False,
          session=None, now=None)->dict:
    football=single_provider("football_data_org",football_key,
        "https://api.football-data.org/v4/competitions","X-Auth-Token",
        "competitions",session=session)
    # LiveTennisAPI's free entitlement has NOT been established. No speculative
    # consumption of a plan, including usage endpoint, without explicit opt-in.
    tennis=(single_provider("live_tennis_api",tennis_key,
        "https://api.livetennisapi.com/api/public/v1/matches",
        "X-API-Key","data",params={"status":"upcoming","limit":5},
        session=session) if tennis_opt_in else
        {"status":"ENTITLEMENT_NOT_ATTESTED_NO_REQUEST",
         "authenticated":False,"data_verified":False,
         "calls":0,"token_redacted":True})
    result={"schema":"MATRIX_FREE_API_INDEPENDENT_PROBE_V2",
        "generated_at_utc":(now or datetime.now(timezone.utc)).isoformat(),
        "providers":{"football_data_org":football,"live_tennis_api":tennis},
        "network_calls":football["calls"]+tennis["calls"],
        "live_tennis_opt_in":tennis_opt_in,
        "status":"PARTIAL_VERIFIED" if any(p["data_verified"]
                      for p in (football,tennis)) else "NO_VERIFIED_LIVE_PROVIDER",
        "promotion_gate":{"automatic_model_feed":False,
                          "requires_independent_coverage_identity_and_pit_certification":True,
                          "production_feed_authorized":False},
        "protections":{"secrets_persisted":False,"secrets_echoed":False,
                       "paid_api_subscription_authorized":False,
                       "real_money":"BLOCKED","automatic_wagering":False}}
    return result

def main():
    report=probe(os.getenv("FOOTBALL_DATA_ORG_KEY","").strip(),
                 os.getenv("LIVE_TENNIS_API_KEY","").strip(),
                 tennis_opt_in=os.getenv("MATRIX_LIVE_TENNIS_PROBE_OPT_IN")=="true")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"network_calls":report["network_calls"],
      "providers":{k:v["status"] for k,v in report["providers"].items()},
      "real_money":"BLOCKED","production_feed_authorized":False},sort_keys=True))

if __name__=="__main__":main()
