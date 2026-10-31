from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BOGOTA=ZoneInfo("America/Bogota")
CUTOFF=date(2026,10,28)

TENNIS_RECEIPT=Path("evidence/tennis/paid_window_harvest/2026-10-22/MATRIX_RAPIDAPI_TENNIS_HARVEST_RECEIPT_LAST.json")
FOOTBALL_ROOT=Path("evidence/api_football/prospective_daily")


def _dt(value:str)->datetime:
    return datetime.fromisoformat(value.replace("Z","+00:00"))


def _latest_football_summary()->tuple[Path,dict]:
    rows=[]
    if FOOTBALL_ROOT.exists():
        for p in FOOTBALL_ROOT.glob("*/*/cycle_summary.json"):
            try:
                j=json.loads(p.read_text(encoding="utf-8"))
                stamp=_dt(str(j.get("finished_at_utc") or j.get("started_at_utc")))
                rows.append((stamp,p,j))
            except Exception:
                continue
    if not rows:
        raise SystemExit("PAID_API_UTILIZATION_FOOTBALL_EVIDENCE_MISSING")
    _,p,j=max(rows,key=lambda x:x[0])
    return p,j


def evaluate(now_utc:datetime|None=None)->dict:
    now_utc=now_utc or datetime.now(timezone.utc)
    bog_date=now_utc.astimezone(BOGOTA).date()
    active=bog_date<=CUTOFF
    out={
      "schema":"MATRIX_PAID_API_UTILIZATION_WATCHDOG_V1",
      "generated_at_utc":now_utc.replace(microsecond=0).isoformat(),
      "bogota_date":bog_date.isoformat(),
      "cutoff_bogota_date":CUTOFF.isoformat(),
      "paid_window_active":active,
      "real_money":"BLOCKED",
      "checks":{},
      "status":"PASS",
    }
    if not active:
        out["status"]="PASS_WINDOW_CLOSED_NO_RENEWAL"
        return out

    failures=[]
    if not TENNIS_RECEIPT.exists():
        failures.append("TENNIS_HARVEST_MISSING")
        out["checks"]["tennis"]={"status":"FAIL","reason":"HARVEST_MISSING"}
    else:
        j=json.loads(TENNIS_RECEIPT.read_text(encoding="utf-8"))
        age=(now_utc-_dt(j["generated_at_utc"])).total_seconds()/3600
        ok=age<=8.5
        out["checks"]["tennis"]={
          "status":"PASS" if ok else "FAIL",
          "age_hours":round(age,3),
          "max_age_hours":8.5,
          "unique_match_count":int(j.get("unique_match_count") or 0),
          "network_calls":int(j.get("network_calls") or 0),
          "provider_inventory_complete":bool(j.get("provider_inventory_complete",False)),
        }
        if not ok: failures.append("TENNIS_HARVEST_STALE")

    try:
        p,j=_latest_football_summary()
        age=(now_utc-_dt(j["finished_at_utc"])).total_seconds()/3600
        ok=age<=20.5
        out["checks"]["football"]={
          "status":"PASS" if ok else "FAIL",
          "age_hours":round(age,3),
          "max_age_hours":20.5,
          "cycle_path":str(p),
          "network_calls_performed":int(j.get("network_calls_performed") or 0),
          "fixtures_received":int((j.get("fixture_capture") or {}).get("fixtures_received") or 0),
          "cycle_status":j.get("status"),
        }
        if not ok: failures.append("FOOTBALL_PAID_CYCLE_STALE")
    except SystemExit:
        failures.append("FOOTBALL_PAID_CYCLE_MISSING")
        out["checks"]["football"]={"status":"FAIL","reason":"PAID_CYCLE_MISSING"}

    out["failures"]=failures
    out["status"]="PASS" if not failures else "FAIL_PAID_WINDOW_UNDERUTILIZED"
    return out


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="evidence/governance/MATRIX_PAID_API_UTILIZATION_WATCHDOG_LAST.json")
    p.add_argument("--fail-on-underutilization",action="store_true")
    a=p.parse_args()
    result=evaluate()
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
    if a.fail_on_underutilization and result["status"].startswith("FAIL"):
        raise SystemExit(result["status"])


if __name__=="__main__":
    main()
