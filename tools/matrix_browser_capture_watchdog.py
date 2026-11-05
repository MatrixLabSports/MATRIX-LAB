"""Read-only decision for GitHub Actions browser-quote capture failover.

Does not inspect bets, money, prices, secrets or credentials. An external
GitHub Actions workflow may dispatch ONLY the already existing PAPER/SHADOW
browser workflow if it has gone stale.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone

def utc(value):
    d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if d.utcoffset() is None:
        raise ValueError("WATCHDOG_TIMESTAMP_MUST_BE_AWARE")
    return d.astimezone(timezone.utc)

def check(workflow_runs,*,now,max_age_seconds=720):
    if now.tzinfo is None:
        raise ValueError("WATCHDOG_CLOCK_MUST_BE_AWARE")
    if not isinstance(workflow_runs,list):
        raise ValueError("WATCHDOG_RUN_LIST_INVALID")
    if not workflow_runs:
        return {"dispatch":True,"reason":"NO_BROWSER_CAPTURE_RUNS",
                "last_run_id":None,"last_run_age_seconds":None}
    valid=[]
    for entry in workflow_runs:
        if not isinstance(entry,dict):
            continue
        try:
            created=utc(entry["created_at"])
            run_id=int(entry["id"])
            if run_id<=0:
                continue
            valid.append((created,run_id,entry))
        except (KeyError,ValueError,TypeError):
            continue
    if not valid:
        raise ValueError("WATCHDOG_NO_VALID_PROVIDER_RUNS")
    created,run_id,entry=max(valid,key=lambda v:(v[0],v[1]))
    age=(now.astimezone(timezone.utc)-created).total_seconds()
    if age < -120:
        return {"dispatch":False,"reason":"CLOCK_DRIFT_OR_FUTURE_PROVIDER_TIMESTAMP",
                "last_run_id":run_id,"last_run_age_seconds":round(age)}
    if age < 0:
        age=0
    status=str(entry.get("status") or "")
    conclusion=str(entry.get("conclusion") or "")
    # An indefinitely queued self-hosted job does not mean healthy capture.
    # Never dispatch a duplicate: GitHub cannot start a Windows listener.
    if status in ("queued","waiting","requested","pending") and age>max_age_seconds:
        return {"dispatch":False,"reason":"BROWSER_RUN_QUEUED_OVERDUE_LOCAL_RUNNER_REQUIRED",
                "runner_recovery_required":True,
                "last_run_id":run_id,"last_run_age_seconds":round(age)}
    if status in ("queued","in_progress","waiting","requested","pending"):
        return {"dispatch":False,"reason":"BROWSER_RUN_ALREADY_PENDING",
                "runner_recovery_required":False,
                "last_run_id":run_id,"last_run_age_seconds":round(age)}
    if status=="completed" and conclusion=="success" and age<=max_age_seconds:
        return {"dispatch":False,"reason":"RECENT_SUCCESSFUL_BROWSER_RUN",
                "last_run_id":run_id,"last_run_age_seconds":round(age)}
    if status=="completed" and conclusion in ("failure","timed_out","cancelled"):
        return {"dispatch":True,"reason":"LAST_BROWSER_RUN_NOT_SUCCESSFUL",
                "last_run_id":run_id,"last_run_age_seconds":round(age)}
    if status=="completed" and conclusion=="success" and age>max_age_seconds:
        return {"dispatch":True,"reason":"LAST_BROWSER_RUN_STALE",
                "last_run_id":run_id,"last_run_age_seconds":round(age)}
    return {"dispatch":False,"reason":"UNKNOWN_BROWSER_RUN_STATE_FAIL_CLOSED",
            "last_run_id":run_id,"last_run_age_seconds":round(age)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--runs-json",required=True)
    p.add_argument("--max-age-seconds",type=int,default=720)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    with open(a.runs_json,encoding="utf-8") as f:
        obj=json.load(f)
    if a.max_age_seconds<300:
        raise SystemExit("WATCHDOG_AGE_TOO_SHORT")
    decision=check(obj["workflow_runs"],now=datetime.now(timezone.utc),
                   max_age_seconds=a.max_age_seconds)
    out={"schema":"MATRIX_BROWSER_CAPTURE_WATCHDOG_V1",
         "checked_at_utc":datetime.now(timezone.utc).isoformat(),
         **decision,"real_money":"BLOCKED",
         "automatic_wagering":False,"telegram_signal_authorized":False,
         "research_only":True}
    with open(a.output,"w",encoding="utf-8") as f:
        json.dump(out,f,indent=2,sort_keys=True)
    print(json.dumps(out,sort_keys=True))

if __name__=="__main__":
    main()
