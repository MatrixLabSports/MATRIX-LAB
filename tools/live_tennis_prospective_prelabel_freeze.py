"""Append-only, no-API prelabel snapshots of genuinely captured Live Tennis states.

Captures before settlement on the day the collector runs. Never backfills
old labeled ledgers, reassigns match IDs or opens production probabilities.
A label-free freeze is NOT yet independently certified PIT/chronological OOS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from tools.live_tennis_presettlement_builder import fold_for_match
from tools.live_tennis_cumulative_integrity_research import parse_utc

BASE=Path("evidence/live_tennis_lab")
LEDGER="MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"
OUT="MATRIX_LIVE_TENNIS_PRELABEL_FREEZE_RECEIPT_LAST.json"
ARCHIVE="prelabel_immutable"
SCHEMA="MATRIX_LIVE_TENNIS_PRELABEL_CAPTURE_BATCH_V1"
REPORT="MATRIX_LIVE_TENNIS_PRELABEL_FREEZE_RECEIPT_V1"
# Explicit source-side live feature subset: never export final result labels,
# settlements, post-match metadata, or unlisted future provider fields.
FROZEN_STATE_FIELDS = (
    "provider","match_id","state_key","sequence","captured_at_utc",
    "response_sha256","tour","gender","surface","tournament","round",
    "round_code","p1_name","p2_name","p1_ranking","p2_ranking",
    "quality_state_valid","origin","stale","corroborated","sources_count",
    "sets_p1","sets_p2","set_diff_p1","games_by_set_p1",
    "games_by_set_p2","total_game_diff_p1","current_set_index_zero_based",
    "current_set_game_diff_p1","point_p1_code","point_p2_code",
    "point_diff_p1","point_p1_raw","point_p2_raw","server","server_is_p1",
    "is_tiebreak","age_seconds","observed_age_seconds","ranking_advantage_p1",
)
FORBIDDEN_RESULT_FIELDS = {
    "p1_match_win","label_opened","settlement_status","winner",
    "result_version","result_restated_at","final_result",
}
if FORBIDDEN_RESULT_FIELDS.intersection(FROZEN_STATE_FIELDS):
    raise ValueError("RESULT_FIELD_INCLUDED_IN_PRELABEL_SNAPSHOT_ALLOWLIST")

def sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def _read(path:Path)->tuple[dict,bytes]:
    raw=path.read_bytes()
    if len(raw)>15_000_000:
        raise ValueError("PRELABEL_INPUT_OVERSIZED")
    obj=json.loads(raw)
    if not isinstance(obj,dict):
        raise ValueError("PRELABEL_INPUT_NOT_JSON_OBJECT")
    return obj,raw

def _snapshot_existing(archive:Path)->set[str]:
    seen=set()
    for path in sorted(archive.glob("MATRIX_LIVE_PRELABEL_BATCH_*.json")):
        data,_=_read(path)
        if (data.get("schema")!=SCHEMA or data.get("label_opened") is not False
            or data.get("outcomes_read")!=0 or data.get("real_money")!="BLOCKED"
            or data.get("model_probability_authorized") is not False):
            raise ValueError("UNTRUSTED_PREEXISTING_PRELABEL_BATCH")
        source_hash=data.get("source_raw_sha256")
        if not isinstance(source_hash,str) or len(source_hash)!=64:
            raise ValueError("PRELABEL_SNAPSHOT_SOURCE_HASH_MISSING")
        raw_path=archive/("MATRIX_LIVE_PRELABEL_RAW_"+source_hash+".json")
        if not raw_path.is_file() or sha(raw_path.read_bytes())!=source_hash:
            raise ValueError("PRELABEL_ORIGINAL_SOURCE_RAW_HASH_MISMATCH")
        if "frozen_state_snapshot_sha256" in data:
            state_hash=data["frozen_state_snapshot_sha256"]
            snapshot=archive/("MATRIX_LIVE_PRELABEL_STATES_"+source_hash+".json")
            if (not snapshot.is_file()
                or sha(snapshot.read_bytes())!=state_hash):
                raise ValueError("PRELABEL_IMMUTABLE_LIVE_STATE_SNAPSHOT_CHANGED")
            payload,_=_read(snapshot)
            states=payload.get("states")
            if (not isinstance(states,list)
                or payload.get("schema")!="MATRIX_LIVE_TENNIS_LABEL_FREE_STATES_V1"
                or payload.get("source_raw_sha256")!=source_hash
                or payload.get("real_money")!="BLOCKED"):
                raise ValueError("PRELABEL_FROZEN_STATE_SNAPSHOT_SCHEMA_INVALID")
            if any(
                not isinstance(row,dict) or
                FORBIDDEN_RESULT_FIELDS.intersection(row) or
                not set(row).issubset(FROZEN_STATE_FIELDS)
                for row in states
            ):
                raise ValueError("PRELABEL_FROZEN_SNAPSHOT_CONTAINS_RESULT_FIELD")
        for rec in data.get("matches") or []:
            key=rec.get("physical_match_key")
            if not isinstance(key,str) or key in seen:
                raise ValueError("PRELABEL_DUPLICATE_OR_MALFORMED_IMMUTABLE_MATCH_ID")
            seen.add(key)
    return seen

def collect(root:Path,day:str,*,now:datetime|None=None)->dict:
    date.fromisoformat(day)
    observed=(now or datetime.now(timezone.utc))
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("FREEZE_TIMESTAMP_MUST_HAVE_TIMEZONE")
    observed=observed.astimezone(timezone.utc)
    folder=root/BASE/day
    folder.mkdir(parents=True,exist_ok=True)
    archive=folder/ARCHIVE
    archive.mkdir(parents=True,exist_ok=True)
    before=_snapshot_existing(archive)
    source_path=folder/LEDGER
    report={
        "schema":REPORT,"operational_date_bogota":day,
        "generated_at_utc":observed.isoformat(),
        "status":"NO_CURRENT_CAPTURE_LEDGER",
        "source_ledger_path":source_path.relative_to(root).as_posix(),
        "source_raw_sha256":None,
        "previously_frozen_unique_match_keys":len(before),
        "newly_frozen_unique_match_keys":0,
        "source_current_unique_match_keys":None,
        "unfrozen_match_keys_in_this_capture":None,
        "label_free_observation_only":True,
        "before_final_result_independently_certified":False,
        "prospective_pit_and_oos_authorized":False,
        "original_hard_clay_models_modified":False,
        "production_model_probability_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    if source_path.exists():
        doc,raw=_read(source_path)
        report["source_raw_sha256"]=sha(raw)
        protections=doc.get("protections") or {}
        if (doc.get("schema")!="MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1"
            or doc.get("operational_date_bogota")!=day
            or protections.get("real_money")!="BLOCKED"
            or protections.get("odds_to_probability") is not False
            or protections.get("automatic_wagering") is not False
            or protections.get("outcomes_read_during_live_capture")!=0
            or protections.get("secrets_persisted") is not False):
            raise ValueError("UNSAFE_CURRENT_LIVE_LEDGER_NOT_FROZEN")
        states=doc.get("states")
        if not isinstance(states,list):
            raise ValueError("PRELABEL_STATES_NOT_ARRAY")
        current={}
        labeled_keys=set()
        source_labeled_rows=0
        for row in states:
            if not isinstance(row,dict):
                raise ValueError("PRELABEL_STATE_ROW_NOT_OBJECT")
            mid=row.get("match_id")
            if (type(mid) is not int or mid<=0
                or row.get("provider")!="live_tennis_api"):
                raise ValueError("PRELABEL_MISSING_MATCH_SOURCE_IDENTITY")
            key="live_tennis_api:"+str(mid)
            if (row.get("label_opened") is True
                or row.get("p1_match_win") is not None
                or row.get("settlement_status")!="PENDING_FINAL"):
                labeled_keys.add(key)
                source_labeled_rows+=1
            captured=parse_utc(row.get("captured_at_utc"))
            if captured>observed:
                raise ValueError("PRELABEL_STATE_CAPTURE_AFTER_FREEZE")
            current.setdefault(key,[]).append(row)
        report["source_current_unique_match_keys"]=len(current)
        newcomers=sorted(set(current)-before)
        # Completed prior matches can coexist in a daily append-only ledger.
        # Quarantine the whole physical match ID if ANY state is labeled:
        # never hide a completed state by selecting an earlier unlabeled row.
        eligible_new=[key for key in newcomers if key not in labeled_keys]
        def eligible_live_rows(key):
            return [
                row for row in current[key]
                if row.get("quality_state_valid") is True
                and row.get("origin")=="observed"
                and row.get("stale") is False
                and type(row.get("sets_p1")) is int
                and type(row.get("sets_p2")) is int
                and 0<=row["sets_p1"]<2 and 0<=row["sets_p2"]<2
                and 0 <= (observed-parse_utc(row["captured_at_utc"])).total_seconds() <= 1800
            ]
        fresh={key:eligible_live_rows(key) for key in eligible_new}
        fresh={key:rows for key,rows in fresh.items() if rows}
        report["source_labeled_rows_quarantined"]=source_labeled_rows
        report["source_labeled_physical_match_keys_quarantined"]=len(labeled_keys)
        report["source_contains_prior_final_labels"]=bool(labeled_keys)
        report["unfrozen_match_keys_in_this_capture"]=len(newcomers)
        report["source_new_match_keys_with_fresh_valid_state"]=len(fresh)
        report["source_unfrozen_stale_or_low_quality_match_keys"]=len(eligible_new)-len(fresh)
        if not states:
            report["status"]="CURRENT_CAPTURE_HAS_NO_GENUINE_STATES"
        elif not newcomers:
            report["status"]="NO_NEW_UNLABELED_MATCHES_TO_FREEZE"
        elif not fresh and labeled_keys:
            report["status"]="BLOCKED_NO_SAFE_UNLABELED_NEW_MATCH_IN_MIXED_LEDGER"
        elif not fresh:
            report["status"]="BLOCKED_NO_NEW_FRESH_QUALITY_VALID_LIVE_STATE"
        else:
            manifests=[]
            frozen_rows=[]
            for key,states_for_match in sorted(fresh.items()):
                mid=int(key.split(":")[-1])
                times=sorted(parse_utc(x["captured_at_utc"]) for x in states_for_match)
                for row in states_for_match:
                    frozen_row={field:row[field] for field in FROZEN_STATE_FIELDS
                                if field in row}
                    if FORBIDDEN_RESULT_FIELDS.intersection(frozen_row):
                        raise ValueError("PRELABEL_RESULT_LEAK_IN_NEW_FROZEN_STATE")
                    frozen_rows.append(frozen_row)
                fold=fold_for_match(mid)
                manifests.append({
                    "physical_match_key":key,
                    "match_id":mid,
                    "split":"HOLDOUT" if fold==4 else "DEVELOPMENT",
                    "fold_5":fold,
                    "captured_live_state_count":len(states_for_match),
                    "first_captured_at_utc":times[0].isoformat(),
                    "last_captured_at_utc":times[-1].isoformat(),
                    "final_outcome":None,
                    "no_betting_data_used":True,
                })
            source_hash=sha(raw)
            target_raw=archive/("MATRIX_LIVE_PRELABEL_RAW_"+source_hash+".json")
            batch_path=archive/("MATRIX_LIVE_PRELABEL_BATCH_"+source_hash+".json")
            snapshot_path=archive/("MATRIX_LIVE_PRELABEL_STATES_"+source_hash+".json")
            snapshot={
                "schema":"MATRIX_LIVE_TENNIS_LABEL_FREE_STATES_V1",
                "source_raw_sha256":source_hash,
                "states":frozen_rows,
                "source_contains_other_prior_final_labels":bool(labeled_keys),
                "original_source_ledger_is_unchanged":True,
                "future_independent_kickoff_certification_pending":True,
                "production_probability_authorized":False,
                "real_money":"BLOCKED",
            }
            snapshot_bytes=(json.dumps(snapshot,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode("utf-8")
            snapshot_hash=sha(snapshot_bytes)
            batch={
                "schema":SCHEMA,
                "target_date_bogota":day,
                "frozen_at_utc":observed.isoformat(),
                "source_ledger_path":source_path.relative_to(root).as_posix(),
                "source_raw_sha256":source_hash,
                "no_outcome_values_in_source":not bool(labeled_keys),
                "source_contains_other_prior_final_labels":bool(labeled_keys),
                "unlabeled_eligible_matches_have_no_final_labels":True,
                "frozen_state_snapshot_sha256":snapshot_hash,
                "frozen_state_count":len(frozen_rows),
                "frozen_state_fields_allowlisted":True,
                "label_opened":False,
                "outcomes_read":0,
                "source_state_count":len(states),
                "new_unique_match_count":len(manifests),
                "matches":manifests,
                "split_group":"PROVIDER_PLUS_MATCH_ID",
                "split_rule":"EXISTING_SHA256_MATRIX_LIVE_TENNIS_V0_1_MATCH_ID_FOLD_4_HOLDOUT",
                "same_match_train_test_forbidden":True,
                "source_state_snapshot_immutable":True,
                "future_independent_final_time_verification_pending":True,
                "model_probability_authorized":False,
                "telegram_signal_authorized":False,
                "automatic_wagering":False,
                "real_money":"BLOCKED",
            }
            frozen_bytes=(json.dumps(batch,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode("utf-8")
            if target_raw.exists() and target_raw.read_bytes()!=raw:
                raise ValueError("PRELABEL_SOURCE_HASH_PATH_CONFLICT")
            if batch_path.exists() and batch_path.read_bytes()!=frozen_bytes:
                raise ValueError("PRELABEL_BATCH_IMMUTABILITY_CONFLICT")
            if snapshot_path.exists() and snapshot_path.read_bytes()!=snapshot_bytes:
                raise ValueError("PRELABEL_STATE_SNAPSHOT_IMMUTABILITY_CONFLICT")
            if not target_raw.exists():
                target_raw.write_bytes(raw)
            if sha(target_raw.read_bytes())!=source_hash:
                raise ValueError("PRELABEL_FROZEN_SOURCE_HASH_WRITE_ERROR")
            if not snapshot_path.exists():
                snapshot_path.write_bytes(snapshot_bytes)
            if sha(snapshot_path.read_bytes())!=snapshot_hash:
                raise ValueError("PRELABEL_FROZEN_STATE_HASH_WRITE_ERROR")
            if not batch_path.exists():
                batch_path.write_bytes(frozen_bytes)
            report["status"]="FROZEN_NEW_UNLABELED_LIVE_MATCHES_RESEARCH_ONLY"
            report["newly_frozen_unique_match_keys"]=len(manifests)
            report["unfrozen_match_keys_in_this_capture"]=len(newcomers)-len(fresh)
            report["immutable_new_batch_path"]=batch_path.relative_to(root).as_posix()
            report["immutable_new_batch_sha256"]=sha(batch_path.read_bytes())
            report["immutable_label_free_states_path"]=snapshot_path.relative_to(root).as_posix()
            report["immutable_label_free_states_sha256"]=snapshot_hash
            report["immutable_label_free_state_count"]=len(frozen_rows)
    receipt=folder/OUT
    receipt.write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--date",required=True)
    ap.add_argument("--root",type=Path,default=Path("."))
    args=ap.parse_args()
    r=collect(args.root,args.date)
    print(json.dumps({k:r.get(k) for k in (
        "status","source_current_unique_match_keys",
        "previously_frozen_unique_match_keys","newly_frozen_unique_match_keys",
        "unfrozen_match_keys_in_this_capture",
        "production_model_probability_authorized",
    )},sort_keys=True))

if __name__=="__main__":
    main()
