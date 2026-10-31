from __future__ import annotations
import json, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_SELF_HOSTED_BROWSER_HEALTH_LAST.json"

def main():
    endpoint=os.environ.get("MATRIX_BROWSER_CDP_ENDPOINT","http://127.0.0.1:9222").rstrip("/")
    version_url=endpoint+"/json/version"
    ok=False; payload={}; error=None
    try:
        with urllib.request.urlopen(version_url,timeout=5) as r:
            payload=json.loads(r.read().decode("utf-8"))
        ok=bool(payload.get("webSocketDebuggerUrl"))
    except Exception as e:
        error=type(e).__name__
    out={
      "schema":"MATRIX_SELF_HOSTED_BROWSER_HEALTH_V1",
      "checked_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "endpoint":endpoint,
      "status":"PASS_CDP_REACHABLE" if ok else "NO_GO_CDP_UNREACHABLE",
      "browser":payload.get("Browser"),
      "protocol_version":payload.get("Protocol-Version"),
      "websocket_present":bool(payload.get("webSocketDebuggerUrl")),
      "error":error,
      "automatic_wagering":False,
      "real_money":"BLOCKED"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(out,sort_keys=True))
    if not ok:
        raise SystemExit("MATRIX_SELF_HOSTED_BROWSER_CDP_NO_GO")

if __name__=="__main__":
    main()
