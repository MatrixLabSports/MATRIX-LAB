from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

from tools.telegram_green_signal_alerts import (
    exact_over25_offer,
    physical_book_over25_offer,
    parse_dt,
)
from tools.matrix_quote_recovery_evidence import validate as validate_execution_evidence

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json"
OUT=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_QUOTE_RECOVERY_ACTUATOR_LAST.json"
EXEC_LEDGER=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_QUOTE_RECOVERY_EXECUTION_LEDGER.jsonl"
WINDOW_MINUTES=120

def _load(path:Path)->dict[str,Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def _append(row:dict[str,Any])->None:
    EXEC_LEDGER.parent.mkdir(parents=True,exist_ok=True)
    with EXEC_LEDGER.open("a",encoding="utf-8") as h:
        h.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")

def _already_executed()->set[str]:
    if not EXEC_LEDGER.exists(): return set()
    out=set()
    for line in EXEC_LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: r=json.loads(line)
        except Exception: continue
        if r.get("validated") is True and r.get("fixture_id"):
            out.add(str(r["fixture_id"]))
    return out

def _eligible_rows(audit:dict[str,Any], now:datetime)->list[dict[str,Any]]:
    rows=[]
    for r in audit.get("records") or []:
        if not isinstance(r,dict): continue
        kickoff=parse_dt(r.get("kickoff"))
        if kickoff is None: continue
        sec=(kickoff-now).total_seconds()
        if sec<=0 or sec>WINDOW_MINUTES*60: continue
        if float(r.get("p_matrix") or 0)<0.60: continue
        if r.get("state") not in {
            "WAITING_FINAL_REVALIDATION_WINDOW",
            "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25",
            "BLOCKED_NONPOSITIVE_EV",
            "BLOCKED_NO_FRESH_PINNACLE_REFERENCE",
        }:
            continue
        rows.append(r)
    rows.sort(key=lambda x:parse_dt(x["kickoff"]))
    return rows

def run(api_key:str)->dict[str,Any]:
    now=datetime.now(timezone.utc).replace(microsecond=0)
    audit=_load(AUDIT)
    rows=_eligible_rows(audit,now)
    done=_already_executed()
    session=requests.Session()
    results=[]
    for r in rows:
        fid=str(r["fixture_id"])
        if fid in done:
            results.append({"fixture_id":fid,"status":"ALREADY_EXECUTED_EVIDENCE_PRESENT"})
            continue
        p=float(r["p_matrix"]); kickoff=str(r["kickoff"])
        api_diag={}
        api_offer=exact_over25_offer(session,api_key,fid,p,None,api_diag) if api_key else None
        browser_offer=physical_book_over25_offer(fid,p,now,required_house_key=None)
        offers=[x for x in (api_offer,browser_offer) if isinstance(x,dict)]
        offer=max(offers,key=lambda x:float(x.get("ev") or -999)) if offers else None
        if offer is None:
            results.append({
              "fixture_id":fid,"match":r.get("match"),"kickoff":kickoff,
              "status":"BLOCKED_BROWSER_ACTUATION_CAPABILITY" if not browser_offer else "BLOCKED_NO_VALID_QUOTE",
              "api_football_diagnostic":api_diag,
              "browser_physical_evidence_present":bool(browser_offer),
              "required_next_source":"OPERA_PHYSICAL_QUOTE_EVIDENCE",
            })
            continue
        ev=float(offer.get("ev") or 0.0)
        if ev<0.05 or float(offer.get("odds") or 0)<=1.50:
            results.append({
              "fixture_id":fid,"match":r.get("match"),"kickoff":kickoff,
              "status":"NO_SIGNAL_ECONOMIC_GATE",
              "house":offer.get("house"),"odds":offer.get("odds"),"ev":ev,
            })
            continue
        observed=offer.get("provider_quote_updated_at_utc") or now.isoformat()
        source_evidence=offer.get("physical_evidence_path") or (
            "API-Football:/odds exact authorized bookmaker offer; diagnostic_sha256="+
            hashlib.sha256(json.dumps(api_diag,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        )
        record=validate_execution_evidence({
          "fixture_id":fid,"market":"OVER_2_5","bookmaker":str(offer.get("house") or ""),
          "decimal_odds":float(offer["odds"]),"quote_observed_at_utc":observed,
          "kickoff_utc":kickoff,"p_matrix":p,"revalidated_ev":ev,
          "source_evidence":str(source_evidence),
        })
        _append(record)
        results.append({
          "fixture_id":fid,"match":r.get("match"),"kickoff":kickoff,
          "status":"RECOVERY_EXECUTED_WITH_EVIDENCE",
          "house":record["bookmaker"],"odds":record["decimal_odds"],
          "ev":record["revalidated_ev"],"record_sha256":record["record_sha256"],
          "source_type":"PHYSICAL_BROWSER" if browser_offer is offer else "API_FOOTBALL",
        })
    counts={}
    for x in results: counts[x["status"]]=counts.get(x["status"],0)+1
    out={
      "schema":"MATRIX_QUOTE_RECOVERY_ACTUATOR_V1",
      "generated_at_utc":now.isoformat(),
      "source_audit_generated_at_utc":audit.get("generated_at_utc"),
      "window_minutes":WINDOW_MINUTES,
      "eligible_candidates_in_window":len(rows),
      "results":results,
      "counts":counts,
      "capabilities":{
        "api_football_automatic":True,
        "opera_connector_physical_read_available":True,
        "opera_click_type_automation_available_to_github_actions":False,
        "browser_fallback_requires_physical_quote_evidence_artifact":True,
      },
      "governance":{
        "p_matrix_min":0.60,"decimal_odds_strictly_gt":1.50,"revalidated_ev_min":0.05,
        "no_backfill_after_kickoff":True,"automatic_wagering":False,"real_money":"BLOCKED"
      },
      "status":"PASS_ACTUATOR_RAN" if rows else "PASS_NO_CANDIDATES_IN_FINAL_WINDOW"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    return out

def main():
    out=run(os.environ.get("API_FOOTBALL_KEY","").strip())
    print(json.dumps({"status":out["status"],"eligible":out["eligible_candidates_in_window"],"counts":out["counts"]},sort_keys=True))

if __name__=="__main__":
    main()
