from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json"
QUEUE=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_BROWSER_QUOTE_RECOVERY_QUEUE_LAST.json"
QUOTA=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_ODDS_API_QUOTA_GUARD_LAST.json"
OUT=ROOT/"evidence"/"governance"/"MATRIX_QUOTE_PIPELINE_CERTIFICATION_LAST.json"
POLICY=ROOT/"config"/"MATRIX_QUOTE_PIPELINE_CERTIFICATION_POLICY.json"
EXECUTION_LEDGER=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_QUOTE_RECOVERY_EXECUTION_LEDGER.jsonl"

INFRA_VARS={"EXACT_AUTHORIZED_BOOK_OVER25_QUOTE","PINNACLE_FRESH_REFERENCE","ODDS_PROVIDER_QUOTA_GUARD"}

def _load(path:Path)->dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _utc(v:str)->datetime:
    return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)

def _jsonl(path:Path)->list[dict]:
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def build()->dict:
    a=_load(AUDIT); q=_load(QUEUE); quota=_load(QUOTA); policy=_load(POLICY)
    executions=_jsonl(EXECUTION_LEDGER)
    epoch=_utc(policy["certification_epoch_utc"])
    records=a.get("records") or []
    infra_lost_all=[
        r for r in records
        if r.get("final_disposition")=="PAST_KICKOFF_NO_BACKFILL"
        and r.get("missing_or_failed_variable") in INFRA_VARS
    ]
    infra_lost=[]
    for r in infra_lost_all:
        checked=r.get("checked_at_utc")
        if checked and _utc(checked) > epoch:
            infra_lost.append(r)
    recoverable=[r for r in records if r.get("recoverability")=="RECOVERABLE_WHILE_PREMATCH"]
    waiting=[r for r in records if r.get("final_disposition")=="WAIT_FOR_120_MIN_WINDOW"]
    audit_ts=_utc(a["generated_at_utc"])
    queue_ts=_utc(q["generated_from_audit_at_utc"])
    queue_synced=queue_ts==audit_ts
    queue_mode=q.get("execution_mode")
    queue_only=queue_mode=="QUEUE_ONLY_REQUIRES_QUOTE_RECOVERY_ACTUATOR_EVIDENCE"
    valid_exec_after_epoch=[
        x for x in executions
        if x.get("validated") is True
        and x.get("quote_observed_at_utc")
        and _utc(x["quote_observed_at_utc"]) > epoch
    ]
    exhausted=((quota.get("decision") or {}).get("stage")=="BLOCKED_EXHAUSTED")
    failures=[]
    if infra_lost:
        failures.append("INFRASTRUCTURE_CANDIDATES_LOST_BEFORE_TELEGRAM")
    if not queue_synced:
        failures.append("RECOVERY_QUEUE_NOT_SYNCHRONIZED_WITH_LATEST_AUDIT")
    if exhausted and recoverable and int(q.get("recoverable_prematch_count") or 0)==0:
        failures.append("EXHAUSTED_PROVIDER_WITH_RECOVERABLE_CANDIDATES_AND_EMPTY_QUEUE")
    if queue_only and recoverable and not valid_exec_after_epoch:
        failures.append("RECOVERY_QUEUE_HAS_NO_EXECUTED_PHYSICAL_QUOTE_EVIDENCE")
    if audit_ts <= epoch:
        failures.append("NO_POST_FIX_AUDIT_OBSERVED_YET")
    status="PASS_CERTIFIED_ZERO_INFRASTRUCTURE_LOSS" if not failures else ("PENDING_PROSPECTIVE_CERTIFICATION" if failures==["NO_POST_FIX_AUDIT_OBSERVED_YET"] else "NO_GO_CERTIFICATION_FAILED")
    return {
      "schema":"MATRIX_QUOTE_PIPELINE_CERTIFICATION_V1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "status":status,
      "criteria":{
        "post_fix_infrastructure_loss_count_must_equal":0,
        "recovery_queue_must_match_latest_audit":True,
        "exhausted_provider_must_not_be_waited_on":True,
        "no_backfill_after_kickoff":True
      },
      "observed":{
        "certification_epoch_utc":policy.get("certification_epoch_utc"),
        "audit_generated_at_utc":a.get("generated_at_utc"),
        "audit_record_count":len(records),
        "historic_infrastructure_loss_count_preserved":len(infra_lost_all),
        "post_fix_infrastructure_loss_count":len(infra_lost),
        "recoverable_prematch_count":len(recoverable),
        "waiting_final_window_count":len(waiting),
        "recovery_queue_generated_from_audit_at_utc":q.get("generated_from_audit_at_utc"),
        "recovery_queue_count":q.get("recoverable_prematch_count"),
        "recovery_queue_synced":queue_synced,
        "recovery_queue_execution_mode":queue_mode,
        "valid_recovery_execution_evidence_after_epoch":len(valid_exec_after_epoch),
        "odds_api_stage":(quota.get("decision") or {}).get("stage"),
        "odds_api_http_status":quota.get("http_status")
      },
      "failures":failures,
      "owners":{
        "pipeline":"PRINCIPAL_REALTIME_RELIABILITY_ODDS_ENGINEER",
        "price_mapping":"MARKET_PRICE_MAPPING_ENGINEER",
        "provider_failover":"MARKET_DATA_INTEGRATION_ENGINEER",
        "incident":"OBSERVABILITY_INCIDENT_ENGINEER",
        "telegram_delivery":"TELEGRAM_DELIVERY_ENGINEER"
      },
      "automatic_wagering":False,
      "real_money":"BLOCKED"
    }

def main()->None:
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],**out["observed"]},sort_keys=True))
    if out["status"]=="NO_GO_CERTIFICATION_FAILED":
        raise SystemExit("QUOTE_PIPELINE_CERTIFICATION_NO_GO")

if __name__=="__main__":
    main()
