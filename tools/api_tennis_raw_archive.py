from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tools.cor0203_api_tennis_discovery import ApiTennisDiscoveryClient, _result_list


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture(start: date, stop: date, out_root: Path) -> dict[str, Any]:
    key=os.environ.get("API_TENNIS_KEY","").strip()
    if not key:
        raise ValueError("API_TENNIS_KEY_NOT_CONFIGURED")
    if stop < start:
        raise ValueError("INVALID_DATE_RANGE")
    if (stop-start).days > 7:
        raise ValueError("DATE_RANGE_EXCEEDS_8_DAYS")

    client=ApiTennisDiscoveryClient(key)
    captures=[]
    cursor=start
    while cursor <= stop:
        payload=client._post("get_fixtures",{
            "date_start":cursor.isoformat(),
            "date_stop":cursor.isoformat(),
            "timezone":"UTC",
        })
        raw=(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8")
        day_dir=out_root/cursor.isoformat()
        day_dir.mkdir(parents=True,exist_ok=True)
        raw_path=day_dir/"api_tennis_get_fixtures_raw.json"
        raw_path.write_bytes(raw)
        rows=_result_list(payload)
        captures.append({
            "utc_query_date":cursor.isoformat(),
            "raw_path":str(raw_path),
            "raw_sha256":sha_bytes(raw),
            "raw_bytes":len(raw),
            "fixture_rows":len(rows),
        })
        cursor += timedelta(days=1)

    standings=client.standings()
    standings_raw=(json.dumps(standings,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8")
    standings_path=out_root/"api_tennis_atp_standings_raw.json"
    standings_path.write_bytes(standings_raw)
    standings_rows=_result_list(standings)

    manifest={
        "schema":"MATRIX_API_TENNIS_RAW_ARCHIVE_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider":"api_tennis",
        "date_start":start.isoformat(),
        "date_stop":stop.isoformat(),
        "network_calls":client.request_count,
        "captures":captures,
        "standings":{
            "raw_path":str(standings_path),
            "raw_sha256":sha_bytes(standings_raw),
            "raw_bytes":len(standings_raw),
            "rows":len(standings_rows),
        },
        "secrets_persisted":False,
        "automatic_model_feed":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS"
    }
    mpath=out_root/"manifest.json"
    mpath.write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",required=True)
    p.add_argument("--stop",required=True)
    p.add_argument("--out-root",required=True)
    a=p.parse_args()
    result=capture(date.fromisoformat(a.start),date.fromisoformat(a.stop),Path(a.out_root))
    print(json.dumps({
        "status":result["status"],
        "days":len(result["captures"]),
        "fixture_rows":sum(x["fixture_rows"] for x in result["captures"]),
        "standings_rows":result["standings"]["rows"],
        "network_calls":result["network_calls"],
        "real_money":result["real_money"]
    },sort_keys=True))

if __name__=="__main__":
    main()
