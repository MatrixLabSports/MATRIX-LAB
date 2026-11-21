"""Append-only FINAL receipts and prelabel-to-outcome research chain for Live Tennis.

Never infer the match's actual end time from settlement HTTP response time.
A result observed after a capture freeze is not independent proof it occurred
after that freeze. No model output, calibration, Telegram signals or wagering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from tools.live_tennis_cumulative_integrity_research import parse_utc
from tools.live_tennis_presettlement_builder import fold_for_match
from tools.live_tennis_prospective_prelabel_freeze import (
    ARCHIVE as PRELABEL_ARCHIVE,
    FORBIDDEN_RESULT_FIELDS,
    FROZEN_STATE_FIELDS,
    SCHEMA as PRELABEL_SCHEMA,
)

BASE = Path("evidence/live_tennis_lab")
FINAL = "MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1.json"
FINALS_ARCHIVE = "settlement_immutable"
PRELABEL_PREFIX = "MATRIX_LIVE_PRELABEL_BATCH_"
REPORT = "MATRIX_LIVE_TENNIS_PRELABEL_FINAL_LINK_RESEARCH_V1"

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def json_bytes(path: Path) -> tuple[dict,bytes]:
    raw=path.read_bytes()
    if len(raw)>15_000_000:
        raise ValueError("LIVE_PROVENANCE_SOURCE_OVERSIZED")
    item=json.loads(raw)
    if not isinstance(item,dict):
        raise ValueError("LIVE_PROVENANCE_JSON_NOT_OBJECT")
    return item,raw

def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()

def _validate_final(doc:dict, day:str)->list[dict]:
    expected=(BASE/day/"MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json").as_posix()
    protected=doc.get("protections") or {}
    if (doc.get("schema")!="MATRIX_LIVE_TENNIS_SETTLEMENT_SYNC_V0_1"
        or doc.get("source_ledger")!=expected
        or protected.get("real_money")!="BLOCKED"
        or protected.get("final_only") is not True
        or protected.get("odds_to_probability") is not False):
        raise ValueError("FINAL_PROVIDER_REPORT_NOT_GOVERNED")
    records=doc.get("standard_final_settlements")
    if not isinstance(records,list):
        raise ValueError("FINAL_PROVIDER_SETTLEMENTS_NOT_ARRAY")
    parse_utc(doc.get("generated_at_utc"))
    return records

def archive_current_final(folder:Path, day:str)->str|None:
    current=folder/FINAL
    if not current.is_file():
        return None
    obj,raw=json_bytes(current)
    _validate_final(obj,day)
    arc=folder/FINALS_ARCHIVE
    arc.mkdir(exist_ok=True,parents=True)
    dest=arc/("MATRIX_LIVE_FINAL_SYNC_SHA256_"+sha(raw)+".json")
    if dest.is_file():
        if dest.read_bytes()!=raw:
            raise ValueError("FINAL_REPORT_ARCHIVE_SHA_COLLISION_OR_MUTATION")
    else:
        dest.write_bytes(raw)
    if sha(dest.read_bytes())!=sha(raw):
        raise ValueError("FINAL_REPORT_ARCHIVE_WRITE_NOT_BYTE_IDENTICAL")
    return dest.name

def _read_archive_final(path:Path, day:str)->tuple[list[dict],str]:
    doc,raw=json_bytes(path)
    name=path.stem
    if name.startswith("MATRIX_LIVE_FINAL_SYNC_SHA256_"):
        expected=name.removeprefix("MATRIX_LIVE_FINAL_SYNC_SHA256_")
        if sha(raw)!=expected:
            raise ValueError("FINAL_ARCHIVE_SHA256_IMMUTABILITY_VIOLATION")
    elif name.startswith("MATRIX_LIVE_FINAL_SYNC_GITBLOB_"):
        expected=name.removeprefix("MATRIX_LIVE_FINAL_SYNC_GITBLOB_")
        if git_blob_sha(raw)!=expected:
            raise ValueError("FINAL_ARCHIVE_GIT_BLOB_IMMUTABILITY_VIOLATION")
    else:
        raise ValueError("UNEXPECTED_FINAL_ARCHIVE_FILENAME")
    return _validate_final(doc,day),sha(raw)

def _verified_prelabel_batches(folder:Path)->tuple[dict,list[str]]:
    arc=folder/PRELABEL_ARCHIVE
    batches=sorted(arc.glob(PRELABEL_PREFIX+"*.json"))
    registry={}
    source_shas=[]
    for path in batches:
        batch,_=json_bytes(path)
        if (batch.get("schema")!=PRELABEL_SCHEMA
            or batch.get("real_money")!="BLOCKED"
            or batch.get("model_probability_authorized") is not False
            or batch.get("label_opened") is not False):
            raise ValueError("PRELABEL_SOURCE_PROTECTIONS_INVALID")
        src= batch.get("source_raw_sha256")
        if not isinstance(src,str) or len(src)!=64:
            raise ValueError("PRELABEL_SOURCE_SHA_MISSING")
        raw=arc/("MATRIX_LIVE_PRELABEL_RAW_"+src+".json")
        frozen=arc/("MATRIX_LIVE_PRELABEL_STATES_"+src+".json")
        if not raw.is_file() or sha(raw.read_bytes())!=src:
            raise ValueError("PRELABEL_HISTORICAL_RAW_HASH_INVALID")
        snapshot,snapshot_raw=json_bytes(frozen)
        if (sha(snapshot_raw)!=batch.get("frozen_state_snapshot_sha256")
            or snapshot.get("schema")!="MATRIX_LIVE_TENNIS_LABEL_FREE_STATES_V1"
            or snapshot.get("source_raw_sha256")!=src
            or snapshot.get("real_money")!="BLOCKED"):
            raise ValueError("PRELABEL_FROZEN_STATE_SNAPSHOT_HASH_INVALID")
        source_shas.append(src)
        by_match=defaultdict(list)
        frozen_at=parse_utc(batch.get("frozen_at_utc"))
        for row in snapshot.get("states") or []:
            if not isinstance(row,dict) or not set(row).issubset(FROZEN_STATE_FIELDS):
                raise ValueError("PRELABEL_STATE_NOT_ALLOWLISTED")
            if FORBIDDEN_RESULT_FIELDS.intersection(row):
                raise ValueError("PRELABEL_STATE_CONTAINS_OUTCOME")
            mid=row.get("match_id")
            if type(mid) is not int or mid<=0 or row.get("provider")!="live_tennis_api":
                raise ValueError("PRELABEL_FROZEN_MATCH_IDENTITY_INVALID")
            captured=parse_utc(row.get("captured_at_utc"))
            if captured>frozen_at:
                raise ValueError("FROZEN_STATE_CAPTURE_AFTER_FREEZE")
            by_match["live_tennis_api:"+str(mid)].append(row)
        for item in batch.get("matches") or []:
            key=item.get("physical_match_key")
            mid=item.get("match_id")
            if (type(mid) is not int or mid<=0 or key!="live_tennis_api:"+str(mid)
                or key in registry or key not in by_match
                or item.get("fold_5")!=fold_for_match(mid)
                or item.get("split")!=("HOLDOUT" if fold_for_match(mid)==4 else "DEVELOPMENT")
                or item.get("final_outcome") is not None):
                raise ValueError("PRELABEL_MATCH_MANIFEST_AMBIGUOUS_OR_MODIFIED")
            registry[key]={"batch_raw_sha256":src,
                           "frozen_at_utc":frozen_at,
                           "fold_5":item["fold_5"],
                           "split":item["split"],
                           "state_count":len(by_match[key])}
        if set(by_match)!=set(x.get("physical_match_key") for x in batch.get("matches") or []):
            raise ValueError("PRELABEL_FROZEN_STATES_AND_MATCHES_DISAGREE")
    return registry,source_shas

def link(root:Path,day:str,*,archive_current:bool=True)->dict:
    date.fromisoformat(day)
    folder=root/BASE/day
    arc=folder/FINALS_ARCHIVE
    archived_now=archive_current_final(folder,day) if archive_current else None
    registry,source_shas=_verified_prelabel_batches(folder)
    final_files=sorted(arc.glob("MATRIX_LIVE_FINAL_SYNC_*.json"))
    observed=defaultdict(list)
    receipts=[]
    for path in final_files:
        records,checksum=_read_archive_final(path,day)
        receipts.append({"path":path.relative_to(root).as_posix(),
                         "sha256":checksum,
                         "standard_final_rows":len(records)})
        for rec in records:
            if not isinstance(rec,dict):
                raise ValueError("FINAL_PROVIDER_MATCH_ROW_NOT_OBJECT")
            mid=rec.get("match_id")
            if type(mid) is not int or mid<=0:
                raise ValueError("FINAL_PROVIDER_MATCH_ID_INVALID")
            if (rec.get("status")!="completed"
                or rec.get("outcome")!="completed"
                or type(rec.get("winner")) is not int
                or rec["winner"] not in (1,2)
                or type(rec.get("result_version")) is not int
                or rec["result_version"]<1):
                raise ValueError("FINAL_PROVIDER_ROW_NOT_STANDARD_COMPLETED")
            seen=parse_utc(rec.get("settled_at_utc"))
            observed["live_tennis_api:"+str(mid)].append({
                "seen":seen,
                "winner":rec["winner"],
                "version":rec["result_version"],
                "restated":rec.get("result_restated_at"),
                "receipt_sha256":checksum,
            })
    entries=[]
    counters=defaultdict(int)
    for key,freeze in sorted(registry.items()):
        finalized=observed.get(key,[])
        row={"physical_match_key":key,
             "prelabel_source_raw_sha256":freeze["batch_raw_sha256"],
             "freeze_at_utc":freeze["frozen_at_utc"].isoformat(),
             "split":freeze["split"],"fold_5":freeze["fold_5"],
             "frozen_state_count":freeze["state_count"],
             "final_winner":None,"final_first_seen_at_utc":None,
             "actual_event_completion_time_independently_verified":False,
             "prospective_holdout_admitted":False,
             "p_live_production_authorized":False}
        if not finalized:
            row["status"]="FINAL_RESULT_NOT_YET_PRESERVED"
        elif any(x["seen"]<=freeze["frozen_at_utc"] for x in finalized):
            row["status"]="FINAL_ALREADY_OBSERVED_BEFORE_OR_AT_FREEZE_QUARANTINED"
        elif len({x["winner"] for x in finalized})!=1:
            row["status"]="FINAL_WINNER_CONFLICT_QUARANTINED"
        elif len({x["version"] for x in finalized})!=1 or any(x["restated"] is not None for x in finalized):
            row["status"]="FINAL_RESTATED_OR_VERSION_DRIFT_NEEDS_INDEPENDENT_REVIEW"
        else:
            first=min(x["seen"] for x in finalized)
            row["status"]="FINAL_OBSERVED_AFTER_FREEZE_ACTUAL_END_TIME_UNVERIFIED"
            row["final_winner"]=finalized[0]["winner"]
            row["final_first_seen_at_utc"]=first.isoformat()
            row["first_observation_lag_seconds"]=int((first-freeze["frozen_at_utc"]).total_seconds())
            row["final_evidence_receipt_sha256"]=sorted({x["receipt_sha256"] for x in finalized})
        counters[row["status"]]+=1
        entries.append(row)
    return {
        "schema":REPORT,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "target_date_bogota":day,
        "source_prelabel_batches":len(source_shas),
        "source_prelabel_raw_sha256":source_shas,
        "frozen_physical_matches":len(registry),
        "archived_current_final_report":archived_now,
        "verified_immutable_final_reports":receipts,
        "verified_immutable_final_report_count":len(receipts),
        "status_counts":dict(sorted(counters.items())),
        "outcome_winner_may_be_used_as_live_model_training_label":False,
        "retrospective_research_only":True,
        "independent_real_match_end_time_certified":False,
        "prospective_training_and_calibration_certified":False,
        "model_probability_authorized":False,
        "telegram_signal_authorized":False,
        "real_money":"BLOCKED",
        "automatic_wagering":False,
        "rows":entries,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--date",required=True)
    ap.add_argument("--root",type=Path,default=Path("."))
    args=ap.parse_args()
    doc=link(args.root,args.date)
    dest=args.root/BASE/args.date/"MATRIX_LIVE_TENNIS_PRELABEL_FINAL_LINK_RESEARCH_LAST.json"
    dest.parent.mkdir(exist_ok=True,parents=True)
    dest.write_text(json.dumps(doc,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"frozen":doc["frozen_physical_matches"],
        "reports":doc["verified_immutable_final_report_count"],
        "status_counts":doc["status_counts"],"production":False},sort_keys=True))

if __name__=="__main__":
    main()
