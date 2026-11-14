from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA="MATRIX_EXTERNAL_TIPSTER_PICK_V1"
TARGET_SAMPLE=100
ALLOWED_RESULTS={"OPEN","WON","LOST","VOID"}
ALLOWED_RELATIONS={"AGREES","DISAGREES","NO_SIGNAL","NOT_COMPARABLE"}


def _dt(value: Any, field: str) -> datetime:
    token=str(value or "").strip()
    if not token:
        raise ValueError(f"{field}_MISSING")
    dt=datetime.fromisoformat(token.replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field}_NOT_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)


def _sha(value: Any) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_pick(row: Mapping[str,Any]) -> tuple[bool,list[str]]:
    errors:list[str]=[]
    if row.get("schema")!=SCHEMA:
        errors.append("SCHEMA_INVALID")
    channel=str(row.get("channel") or "").strip()
    if not channel:
        errors.append("CHANNEL_MISSING")
    pick_id=str(row.get("pick_id") or "").strip()
    if not pick_id:
        errors.append("PICK_ID_MISSING")
    if not str(row.get("sport") or "").strip():
        errors.append("SPORT_MISSING")
    if not str(row.get("event_identity") or "").strip():
        errors.append("EVENT_IDENTITY_MISSING")
    if not str(row.get("market") or "").strip():
        errors.append("MARKET_MISSING")
    if not str(row.get("selection") or "").strip():
        errors.append("SELECTION_MISSING")
    source_message_id=str(row.get("source_message_id") or "").strip()
    source_evidence=str(row.get("source_evidence") or "").strip()
    if not source_message_id and not source_evidence:
        errors.append("SOURCE_EVIDENCE_MISSING")
    try:
        published=_dt(row.get("published_at_utc"),"PUBLISHED_AT")
        start=_dt(row.get("event_start_utc"),"EVENT_START")
        if published>=start:
            errors.append("POST_START_PUBLICATION_FORBIDDEN")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        odds=float(row.get("decimal_odds"))
        if odds<=1.0:
            errors.append("DECIMAL_ODDS_INVALID")
    except Exception:
        errors.append("DECIMAL_ODDS_INVALID")
    result=str(row.get("result") or "").strip().upper()
    if result not in ALLOWED_RESULTS:
        errors.append("RESULT_INVALID")
    relation=str(row.get("matrix_relation") or "NO_SIGNAL").strip().upper()
    if relation not in ALLOWED_RELATIONS:
        errors.append("MATRIX_RELATION_INVALID")
    if row.get("tipster_used_to_generate_p_matrix") is not False:
        errors.append("TIPSTER_TO_P_MATRIX_NOT_EXPLICITLY_FALSE")
    if row.get("automatic_wagering") is not False:
        errors.append("AUTOMATIC_WAGERING_NOT_FALSE")
    if row.get("real_money")!="BLOCKED":
        errors.append("REAL_MONEY_NOT_BLOCKED")
    return (not errors),errors


def settle_flat_one_unit(row: Mapping[str,Any]) -> float | None:
    result=str(row.get("result") or "").strip().upper()
    if result=="OPEN":
        return None
    if result=="VOID":
        return 0.0
    if result=="LOST":
        return -1.0
    if result=="WON":
        return float(row["decimal_odds"])-1.0
    raise ValueError("RESULT_INVALID")


def summarize(rows:list[Mapping[str,Any]], target:int=TARGET_SAMPLE) -> dict[str,Any]:
    seen:set[str]=set()
    valid:list[dict[str,Any]]=[]
    rejected:list[dict[str,Any]]=[]
    for row in rows:
        ok,errors=validate_pick(row)
        pid=str(row.get("pick_id") or "")
        if pid in seen:
            ok=False
            errors=list(errors)+["DUPLICATE_PICK_ID"]
        if ok:
            seen.add(pid)
            valid.append(dict(row))
        else:
            rejected.append({"pick_id":pid or None,"errors":sorted(set(errors))})
    valid.sort(key=lambda x:_dt(x["published_at_utc"],"PUBLISHED_AT"))
    settled=[x for x in valid if str(x.get("result")).upper()!="OPEN"]
    wins=sum(1 for x in settled if str(x.get("result")).upper()=="WON")
    losses=sum(1 for x in settled if str(x.get("result")).upper()=="LOST")
    voids=sum(1 for x in settled if str(x.get("result")).upper()=="VOID")
    pl=sum(settle_flat_one_unit(x) or 0.0 for x in settled)
    odds=[float(x["decimal_odds"]) for x in settled if str(x.get("result")).upper()!="VOID"]
    by_relation={}
    for rel in sorted(ALLOWED_RELATIONS):
        subset=[x for x in settled if str(x.get("matrix_relation") or "NO_SIGNAL").upper()==rel]
        if not subset:
            continue
        rel_pl=sum(settle_flat_one_unit(x) or 0.0 for x in subset)
        rel_nonvoid=[x for x in subset if str(x.get("result")).upper()!="VOID"]
        by_relation[rel]={
            "settled":len(subset),
            "wins":sum(1 for x in subset if str(x.get("result")).upper()=="WON"),
            "losses":sum(1 for x in subset if str(x.get("result")).upper()=="LOST"),
            "voids":sum(1 for x in subset if str(x.get("result")).upper()=="VOID"),
            "flat_one_unit_profit":round(rel_pl,6),
            "roi_pct":round((rel_pl/len(rel_nonvoid))*100.0,4) if rel_nonvoid else None,
        }
    nonvoid=wins+losses
    status="READY_FOR_100_PICK_AUDIT" if len(valid)>=target else "COLLECTING_PHYSICAL_CONSECUTIVE_SAMPLE"
    return {
        "schema":"MATRIX_EXTERNAL_TIPSTER_LAB_SUMMARY_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status":"PASS",
        "lab_state":status,
        "target_consecutive_picks":target,
        "valid_pick_count":len(valid),
        "remaining_to_target":max(0,target-len(valid)),
        "settled_pick_count":len(settled),
        "open_pick_count":len(valid)-len(settled),
        "wins":wins,
        "losses":losses,
        "voids":voids,
        "accuracy_pct":round((wins/nonvoid)*100.0,4) if nonvoid else None,
        "average_decimal_odds":round(sum(odds)/len(odds),6) if odds else None,
        "flat_one_unit_profit":round(pl,6),
        "roi_pct":round((pl/nonvoid)*100.0,4) if nonvoid else None,
        "by_matrix_relation":by_relation,
        "rejected_count":len(rejected),
        "rejections":rejected[:100],
        "sample_sha256":_sha(valid),
        "protections":{
            "consecutive_sample_required":True,
            "cherry_picking_forbidden":True,
            "deleted_or_missing_posts_must_be_flagged_not_silently_removed":True,
            "tipster_used_to_generate_p_matrix":False,
            "tipster_can_auto_promote_market":False,
            "tipster_can_trigger_bet":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def _read_jsonl(path:Path)->list[dict[str,Any]]:
    if not path.exists():
        return []
    out=[]
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip():
            continue
        value=json.loads(line)
        if not isinstance(value,dict):
            raise ValueError(f"EXPECTED_OBJECT_JSONL:{path}:{n}")
        out.append(value)
    return out


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--ledger",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--target",type=int,default=TARGET_SAMPLE)
    args=ap.parse_args()
    result=summarize(_read_jsonl(Path(args.ledger)),target=args.target)
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "lab_state":result["lab_state"],
        "valid_pick_count":result["valid_pick_count"],
        "remaining_to_target":result["remaining_to_target"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
