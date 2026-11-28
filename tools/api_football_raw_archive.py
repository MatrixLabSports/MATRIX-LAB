from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL="https://v3.football.api-sports.io"
TIMEOUT=30
PUBLIC_HEADERS=("x-ratelimit-requests-limit","x-ratelimit-requests-remaining")

def capture(start: date, stop: date, out_root: Path) -> dict[str,Any]:
    key=os.environ.get("API_FOOTBALL_KEY","").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    if stop < start:
        raise ValueError("INVALID_DATE_RANGE")
    if (stop-start).days > 7:
        raise ValueError("DATE_RANGE_EXCEEDS_8_DAYS")
    session=requests.Session()
    captures=[]
    cursor=start
    calls=0
    while cursor<=stop:
        r=session.get(
            BASE_URL+"/fixtures",
            headers={"x-apisports-key":key},
            params={"date":cursor.isoformat(),"timezone":"America/Bogota"},
            timeout=TIMEOUT,
        )
        calls+=1
        body=bytes(r.content)
        if key.encode() in body:
            raise ValueError("API_FOOTBALL_SECRET_ECHO_DETECTED")
        try:
            payload=r.json()
        except Exception as e:
            raise ValueError("API_FOOTBALL_INVALID_JSON") from e
        errors=payload.get("errors") if isinstance(payload,Mapping) else None
        rows=payload.get("response") if isinstance(payload,Mapping) else None
        if not (200 <= int(r.status_code) < 300) or errors not in ({},[],None) or not isinstance(rows,list):
            raise ValueError(f"API_FOOTBALL_PROVIDER_ERROR:{cursor}:{r.status_code}:{errors}")
        day_dir=out_root/cursor.isoformat()
        day_dir.mkdir(parents=True,exist_ok=True)
        raw_path=day_dir/"api_football_fixtures_raw.json"
        raw_path.write_bytes(body)
        captures.append({
            "date_bogota":cursor.isoformat(),
            "raw_path":str(raw_path),
            "raw_sha256":hashlib.sha256(body).hexdigest(),
            "raw_bytes":len(body),
            "fixture_rows":len(rows),
            "public_rate_headers":{k:r.headers.get(k) for k in PUBLIC_HEADERS if r.headers.get(k) is not None},
        })
        cursor+=timedelta(days=1)
    manifest={
        "schema":"MATRIX_API_FOOTBALL_RAW_ARCHIVE_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider":"api_football",
        "date_start":start.isoformat(),
        "date_stop":stop.isoformat(),
        "network_calls":calls,
        "captures":captures,
        "secrets_persisted":False,
        "automatic_model_feed":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    out_root.mkdir(parents=True,exist_ok=True)
    (out_root/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",required=True)
    p.add_argument("--stop",required=True)
    p.add_argument("--out-root",required=True)
    a=p.parse_args()
    m=capture(date.fromisoformat(a.start),date.fromisoformat(a.stop),Path(a.out_root))
    print(json.dumps({
        "status":m["status"],
        "days":len(m["captures"]),
        "fixtures":sum(x["fixture_rows"] for x in m["captures"]),
        "network_calls":m["network_calls"],
        "real_money":m["real_money"],
    },sort_keys=True))

if __name__=="__main__":
    main()
