"""MATRIX Live Tennis: independent, fail-closed research of ALL daily ledgers.

No training, predictions, calibration, model-admission, odds, or betting.
The existing cumulative report remains unchanged; this validates its counts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "MATRIX_LIVE_TENNIS_CUMULATIVE_INTEGRITY_RESEARCH_V1"
LEDGER = "MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json"
CUMULATIVE = "MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1.json"
THRESHOLD = 30  # Existing, unchanged preliminary model-gate research threshold.

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def read_json(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    if len(raw) > 15_000_000:
        raise ValueError("EVIDENCE_OVERSIZED:" + str(path))
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise ValueError("SOURCE_NOT_OBJECT:" + str(path))
    return doc, digest(raw)

def parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("UTC_TIMESTAMP_MISSING")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("UTC_TIMESTAMP_WITHOUT_ZONE")
    return parsed.astimezone(timezone.utc)

def match_key(row: dict) -> str | None:
    mid = row.get("match_id")
    provider = row.get("provider")
    if type(mid) is not int or mid < 1 or not isinstance(provider,str) or not provider.strip():
        return None
    return provider.strip().lower() + ":" + str(mid)

def lane_key(row: dict) -> str:
    return "|".join(str(row.get(k) or "unknown").strip().lower() for k in ("tour","gender","surface"))

def audit(root: Path, *, evidence_root: Path = Path("evidence/live_tennis_lab")) -> dict:
    source_dir = root / evidence_root
    cumulative, cumulative_sha = read_json(source_dir / CUMULATIVE)
    if (cumulative.get("schema") != "MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1"
        or cumulative.get("probability_output_status") != "SEALED"
        or cumulative.get("metrics_status") != "SEALED"
        or cumulative.get("protections",{}).get("real_money") != "BLOCKED"
        or cumulative.get("protections",{}).get("automatic_wagering") is not False):
        raise ValueError("CUMULATIVE_GATE_GOVERNANCE_INVALID")
    expected = cumulative.get("source_ledgers")
    if not isinstance(expected,list):
        raise ValueError("CUMULATIVE_MANIFEST_MISSING")
    actual = sorted(source_dir.glob("*/" + LEDGER))
    rel_actual = {x.relative_to(root).as_posix(): x for x in actual}
    rel_expected = [x.get("path") for x in expected if isinstance(x,dict)]
    if len(rel_expected) != len(expected) or len(set(rel_expected)) != len(rel_expected):
        raise ValueError("CUMULATIVE_MANIFEST_PATHS_DUPLICATED_OR_MALFORMED")
    if set(rel_actual) != set(rel_expected):
        raise ValueError("CUMULATIVE_MANIFEST_DOES_NOT_COVER_ALL_DAILY_LEDGERS")
    records: dict[str,dict] = {}
    invalid: Counter[str] = Counter()
    invalid_sources = []
    source_shas = {}
    observed = 0
    for entry in expected:
        path = str(entry["path"])
        data, sha = read_json(rel_actual[path])
        source_shas[path] = sha
        if sha != entry.get("sha256"):
            raise ValueError("LEDGER_SOURCE_SHA_DRIFT:" + path)
        if data.get("schema") != "MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1":
            raise ValueError("DAILY_LIVE_LEDGER_SCHEMA_INVALID:" + path)
        protections = data.get("protections") or {}
        if (protections.get("real_money") != "BLOCKED"
            or protections.get("automatic_wagering") is not False
            or protections.get("odds_to_probability") is not False
            or protections.get("outcomes_read_during_live_capture") != 0):
            raise ValueError("DAILY_LEDGER_UNSAFE:" + path)
        states = data.get("states")
        if not isinstance(states,list):
            raise ValueError("DAILY_LEDGER_STATES_NOT_ARRAY:" + path)
        for row in states:
            observed += 1
            if not isinstance(row,dict):
                invalid["ROW_NOT_OBJECT"] += 1
                continue
            key = match_key(row)
            if key is None:
                invalid["PHYSICAL_MATCH_ID_OR_PROVIDER_MISSING"] += 1
                continue
            lane = lane_key(row)
            rec = records.setdefault(key, {
                "lanes":set(),"valid_lanes":set(),"settled_lanes":set(),
                "final_labels":set(),"timestamps_bad":False,
                "first_capture":None,"last_capture":None,
                "states":0, "source_dates":set(),
                "has_quality_valid":False,
                "has_final_label":False,
            })
            rec["lanes"].add(lane)
            rec["states"] += 1
            rec["source_dates"].add(str(data.get("operational_date_bogota") or "UNKNOWN"))
            if row.get("quality_state_valid") is True:
                rec["valid_lanes"].add(lane)
                rec["has_quality_valid"] = True
            label = row.get("p1_match_win")
            if (row.get("label_opened") is True
                and row.get("settlement_status") == "FINAL_STANDARD"):
                if type(label) is int and label in (0,1):
                    rec["settled_lanes"].add(lane)
                    rec["final_labels"].add(label)
                    rec["has_final_label"] = True
                else:
                    invalid["SETTLEMENT_FINAL_WITHOUT_BINARY_LABEL"] += 1
            try:
                capture = parse_utc(row.get("captured_at_utc"))
                capture_str = capture.isoformat()
                first = rec["first_capture"]
                last = rec["last_capture"]
                rec["first_capture"] = capture_str if first is None or capture_str < first else first
                rec["last_capture"] = capture_str if last is None or capture_str > last else last
            except (ValueError,TypeError):
                rec["timestamps_bad"] = True
                invalid["MISSING_OR_UNZONED_CAPTURE_TIMESTAMP"] += 1
    cross_lane = sorted(key for key,rec in records.items() if len(rec["lanes"])>1)
    contradictory = sorted(key for key,rec in records.items() if len(rec["final_labels"])>1)
    missing_capture = sorted(key for key,rec in records.items() if rec["timestamps_bad"])
    derived = defaultdict(lambda:{"physical_matches":0,"quality_valid":0,
                                  "final_standard":0,"settled_quality_valid":0})
    for key,rec in records.items():
        for lane in rec["lanes"]:
            derived[lane]["physical_matches"] += 1
            if lane in rec["valid_lanes"]:
                derived[lane]["quality_valid"] += 1
            if lane in rec["settled_lanes"]:
                derived[lane]["final_standard"] += 1
            if lane in rec["valid_lanes"] and lane in rec["settled_lanes"]:
                derived[lane]["settled_quality_valid"] += 1
    mismatches=[]
    for lane,reported in sorted((cumulative.get("lanes") or {}).items()):
        calculated = derived.get(lane,{})
        for old,new in (("unique_match_count","physical_matches"),
                        ("quality_valid_unique_match_count","quality_valid"),
                        ("settled_final_standard_unique_match_count","final_standard"),
                        ("settled_quality_valid_unique_match_count","settled_quality_valid")):
            if reported.get(old) != calculated.get(new,0):
                mismatches.append({"lane":lane,"metric":old,
                                   "reported":reported.get(old),"calculated":calculated.get(new,0)})
    if set(derived) != set(cumulative.get("lanes") or {}):
        mismatches.append({"reason":"SOURCE_LANE_KEYS_DIFFER_FROM_CUMULATIVE_GATE"})
    if len(records) != cumulative.get("global_unique_match_count"):
        mismatches.append({"reason":"GLOBAL_PHYSICAL_MATCH_COUNT_DISAGREES",
                          "reported":cumulative.get("global_unique_match_count"),
                          "calculated":len(records)})
    source_ok=(not invalid and not cross_lane and not contradictory and not missing_capture and not mismatches)
    lanes=[]
    for lane,metrics in sorted(derived.items(), key=lambda x:(-x[1]["settled_quality_valid"],x[0])):
        research_threshold_met = (
            metrics["settled_quality_valid"] >= THRESHOLD
            and all(v not in lane.split("|") for v in ("unknown","none",""))
        )
        lanes.append({
            "lane":lane,
            "settled_quality_valid_unique_match_count":metrics["settled_quality_valid"],
            "research_count_threshold_30_met":research_threshold_met,
            "remaining_to_30":max(0,THRESHOLD-metrics["settled_quality_valid"]),
            "research_integrity_clear":source_ok,
            "model_training_authorized":False,
            "probability_output_authorized":False,
        })
    return {
        "schema":SCHEMA,
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status":"SOURCE_COUNTERS_CONSISTENT_RESEARCH_ONLY" if source_ok else "BLOCKED_SOURCE_INTEGRITY_REVIEW",
        "source_cumulative_report_path":(evidence_root/CUMULATIVE).as_posix(),
        "source_cumulative_sha256":cumulative_sha,
        "source_daily_ledgers":len(actual),
        "source_daily_ledger_hashes":source_shas,
        "states_scanned":observed,
        "physical_unique_matches":len(records),
        "reported_physical_unique_matches":cumulative.get("global_unique_match_count"),
        "multi_lane_same_physical_match_count":len(cross_lane),
        "multi_lane_matches":cross_lane,
        "contradictory_final_result_count":len(contradictory),
        "contradictory_final_match_keys":contradictory,
        "invalid_row_occurrences":dict(sorted(invalid.items())),
        "matches_with_missing_or_bad_capture_timestamp":len(missing_capture),
        "bad_timestamp_match_keys":missing_capture,
        "reported_count_discrepancies":mismatches,
        "lane_research_counts":lanes,
        "research_threshold_30_met_lanes":sum(x["research_count_threshold_30_met"] for x in lanes),
        "source_integrity_passed":source_ok,
        "pre_settlement_freeze_and_independent_kickoff_proof_complete":False,
        "grouped_chronological_oos_validation_complete":False,
        "cross_source_provider_identity_equivalence_certified":False,
        "production_model_training_authorized":False,
        "production_p_live_authorized":False,
        "telegram_signal_authorized":False,
        "no_live_backfill_into_hard_clay":True,
        "real_money":"BLOCKED",
        "automatic_wagering":False,
    }

def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path("."))
    ap.add_argument("--out",type=Path,default=Path(
        "evidence/live_tennis_lab/MATRIX_LIVE_TENNIS_CUMULATIVE_INTEGRITY_RESEARCH_LAST.json"))
    args=ap.parse_args()
    report=audit(args.root)
    dest=args.root/args.out
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in (
        "status","source_daily_ledgers","states_scanned","physical_unique_matches",
        "multi_lane_same_physical_match_count","contradictory_final_result_count",
        "research_threshold_30_met_lanes","production_p_live_authorized"
    )},sort_keys=True))

if __name__=="__main__":
    main()
