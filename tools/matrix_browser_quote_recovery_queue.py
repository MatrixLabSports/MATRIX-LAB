from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json"
QUOTA=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_ODDS_API_QUOTA_GUARD_LAST.json"
OUT=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_BROWSER_QUOTE_RECOVERY_QUEUE_LAST.json"

PREFERRED_BOOKS=["Betano","BetPlay","Betsson","bwin","Codere","Luckia","MrYoker","Rivalo","Rushbet","Sportium","Stake","Wplay"]

def main():
    audit=json.loads(AUDIT.read_text(encoding="utf-8"))
    quota=json.loads(QUOTA.read_text(encoding="utf-8"))
    exhausted=((quota.get("decision") or {}).get("stage")=="BLOCKED_EXHAUSTED")
    rows=[]
    for r in audit.get("records",[]):
        if r.get("time_state_at_audit")!="PREMATCH":
            continue
        if r.get("recoverability")!="RECOVERABLE_WHILE_PREMATCH":
            continue
        if r.get("state")!="BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25":
            continue
        sources=[x for x in r.get("sources_available_for_recovery",[]) if x in PREFERRED_BOOKS]
        rows.append({
            "fixture_id":r.get("fixture_id"),
            "match":r.get("match"),
            "kickoff":r.get("kickoff"),
            "p_matrix":r.get("p_matrix"),
            "current_house":r.get("current_house"),
            "current_odds":r.get("current_odds"),
            "current_ev":r.get("current_ev"),
            "missing_variable":r.get("missing_or_failed_variable"),
            "browser_books":sources,
            "priority":"IMMEDIATE_BROWSER_QUOTE_RECOVERY" if exhausted else "BROWSER_FALLBACK_IF_API_FAILS",
            "required_market":"OVER_2_5",
            "required_checks":["exact authorized bookmaker quote",">1.50","revalidated EV >=0.05","freshness before kickoff"]
        })
    rows.sort(key=lambda x:(x.get("kickoff") or "",-(x.get("p_matrix") or 0)))
    out={
      "schema":"MATRIX_BROWSER_QUOTE_RECOVERY_QUEUE_V1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "odds_api_exhausted":exhausted,
      "policy":{
        "never_wait_for_exhausted_provider":True,
        "switch_to_browser_recovery_immediately":True,
        "source_order":["SofaScore","Flashscore","open execution bookmakers"],
        "real_money":"BLOCKED",
        "automatic_wagering":False,
        "no_backfill_after_kickoff":True
      },
      "recoverable_prematch_count":len(rows),
      "queue":rows
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","odds_api_exhausted":exhausted,"recoverable_prematch_count":len(rows)},sort_keys=True))

if __name__=="__main__":
    main()
