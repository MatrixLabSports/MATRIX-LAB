from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_settlement_ledger import Cor0203SettlementLedger


def _load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _sha(value: Any) -> str:
    body=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def apply_adjudications(
    *,
    adjudications: Mapping[str, Any],
    queue: Mapping[str, Any],
    ledger: Cor0203SettlementLedger,
) -> dict[str, Any]:
    queue_by_id={
        str(row.get("event_id") or ""):row
        for row in queue.get("items",[]) or []
        if row.get("event_id")
    }
    existing={str(row.get("event_id") or "") for row in ledger.load()}
    appended=[]
    waiting=[]
    skipped=[]
    blocked=[]

    for entry in adjudications.get("entries",[]) or []:
        event_id=str(entry.get("event_id") or "")
        if not event_id:
            blocked.append({"event_id":None,"reason":"ADJUDICATION_EVENT_ID_MISSING"})
            continue
        item=queue_by_id.get(event_id)
        if not isinstance(item,Mapping):
            blocked.append({"event_id":event_id,"reason":"ADJUDICATION_QUEUE_EVENT_MISSING"})
            continue

        action=str(entry.get("action") or "")
        if action=="WAIT_FINAL_RESCHEDULED":
            waiting.append({
                "event_id":event_id,
                "reason":"RESCHEDULED_WAITING_FINAL",
                "resumed_start_utc":entry.get("resumed_start_utc"),
                "terminal_status":"NOT_FINAL",
            })
            continue

        if action!="APPEND_SETTLEMENT":
            blocked.append({"event_id":event_id,"reason":"ADJUDICATION_ACTION_UNSUPPORTED:"+action})
            continue

        if event_id in existing:
            skipped.append(event_id)
            continue

        terminal_status=str(entry.get("terminal_status") or "")
        if terminal_status not in {"FINISHED","RETIRED","CANCELLED"}:
            blocked.append({"event_id":event_id,"reason":"ADJUDICATION_TERMINAL_STATUS_INVALID"})
            continue

        outcome=entry.get("outcome_player_a")
        if terminal_status in {"FINISHED","RETIRED"} and not isinstance(outcome,bool):
            blocked.append({"event_id":event_id,"reason":"ADJUDICATION_BINARY_OUTCOME_REQUIRED"})
            continue
        if terminal_status=="CANCELLED" and outcome is not None:
            blocked.append({"event_id":event_id,"reason":"CANCELLED_OUTCOME_MUST_BE_NULL"})
            continue

        sources=list(entry.get("sources") or [])
        if len(sources)<2:
            blocked.append({"event_id":event_id,"reason":"ADJUDICATION_MULTI_SOURCE_REQUIRED"})
            continue

        provider_match_key=str(item.get("provider_match_key") or "")
        if not provider_match_key:
            provider_match_key="adjudicated:"+event_id

        payload={
            "schema":"MATRIX_COR0203_SETTLEMENT_RECORD_V1",
            "event_id":event_id,
            "observation_index":int(item["observation_index"]),
            "observation_sha256":item["observation_sha256"],
            "event_start_utc":item["event_start_utc"],
            "provider_match_key":provider_match_key,
            "provider_result_match_key":provider_match_key,
            "result_source_provider":str(entry.get("source_provider") or "external_multi_source_adjudication"),
            "result_source_reference":" | ".join(str(x) for x in sources),
            "result_payload_sha256":_sha(entry),
            "terminal_status":terminal_status,
            "event_final_result":entry.get("event_final_result"),
            "winner_canonical_name":entry.get("winner_canonical_name"),
            "outcome_player_a":outcome,
            "settled_at_utc":str(adjudications.get("created_at_utc")),
            "settlement_resolution":"MULTI_SOURCE_EXACT_EVENT_ADJUDICATION",
            "metric_eligibility_at_open":entry.get("metric_eligibility_at_open"),
            "metrics_opened":False,
            "used_for_metrics":False,
            "real_money":"BLOCKED",
        }
        ledger.append(payload)
        existing.add(event_id)
        appended.append(event_id)

    audit=ledger.audit()
    return {
        "schema":"MATRIX_COR0203_SETTLEMENT_ADJUDICATION_APPLY_V1",
        "status":"PASS" if not blocked else "PASS_WITH_BLOCKERS",
        "appended_event_ids":appended,
        "appended_count":len(appended),
        "waiting_final":waiting,
        "waiting_final_count":len(waiting),
        "skipped_already_settled":skipped,
        "blocked":blocked,
        "ledger_records":audit.records,
        "hash_chain_verified":audit.hash_chain_verified,
        "outcomes_used_for_metrics":audit.outcomes_used_for_metrics,
        "metrics_opened":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--adjudications",required=True)
    parser.add_argument("--queue",required=True)
    parser.add_argument("--ledger",required=True)
    parser.add_argument("--out",required=True)
    args=parser.parse_args()

    result=apply_adjudications(
        adjudications=_load(Path(args.adjudications)),
        queue=_load(Path(args.queue)),
        ledger=Cor0203SettlementLedger(Path(args.ledger)),
    )
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
    if result["blocked"]:
        raise SystemExit("SETTLEMENT_ADJUDICATION_BLOCKED")


if __name__=="__main__":
    main()
