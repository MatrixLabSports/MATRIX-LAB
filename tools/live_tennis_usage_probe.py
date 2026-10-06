from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
import requests

OUT=Path("evidence/live_tennis_lab/2026-10-06/MATRIX_LIVE_TENNIS_USAGE.json")
URL="https://api.livetennisapi.com/api/public/v1/usage"

def main():
    key=os.environ.get("LIVE_TENNIS_API_KEY","").strip()
    if not key:
        raise SystemExit("LIVE_TENNIS_API_KEY_NOT_CONFIGURED")
    r=requests.get(URL,headers={"X-API-Key":key},timeout=20)
    r.raise_for_status()
    j=r.json()
    if not isinstance(j,dict):
        raise SystemExit("USAGE_PAYLOAD_INVALID")
    j=dict(j)
    if "principal" in j:
        j["principal"]="[REDACTED]"
    payload={
      "schema":"MATRIX_LIVE_TENNIS_USAGE_V1",
      "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "provider":"live_tennis_api",
      "usage":j,
      "protections":{"secret_persisted":False,"real_money":"BLOCKED"}
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","tier":j.get("tier"),"limits":j.get("limits"),"today":j.get("today")},sort_keys=True))
if __name__=="__main__":
    main()
