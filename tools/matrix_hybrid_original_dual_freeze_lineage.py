"""Prove original-formula first-vs-later immutable forecast lineage for OOS.

Settlements MUST use the earliest valid pre-registration. Hybrid prelabel
research can bind a later forecast only when it has the same true event,
SHA-proven raw history and numerically identical probability. Two snapshots
are never two independent match observations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from tools.matrix_independent_free_poisson_oos import stamp
from tools.matrix_hybrid_free_bayesian_v1 import validate_pairs_manifest

SCHEMA = "MATRIX_HYBRID_ORIGINAL_DUAL_FREEZE_LINEAGE_V1"
SOURCE = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json")
OUT = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_ORIGINAL_DUAL_FREEZE_LINEAGE_LAST.json")
FORMULA_SCHEMA = "MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def open_forecast(path: Path):
    raw = path.read_bytes()
    require(len(raw) <= 80000, "FORECAST_SOURCE_TOO_LARGE")
    j = json.loads(raw)
    require(j.get("schema") == FORMULA_SCHEMA and
            j.get("provider") == "FOOTBALL_DATA_ORG" and
            j.get("real_money") == "BLOCKED" and
            j.get("telegram_signal_authorized") is False and
            j.get("production_p_matrix_authorized") is False and
            j.get("frozen_calibrated_model_parameters_mutated") is False,
            "UNTRUSTED_FORECAST_GOVERNANCE")
    return j, sha(raw)


def compare(root: Path, pair: dict):
    fid = str(pair["physical_event_id"])
    require(fid.isdecimal(), "PHYSICAL_EVENT_ID_INVALID")
    kickoff = stamp(pair["event_start_at_utc"])
    # A legitimate Bogotá archive partition can differ from UTC kickoff
    # day, so always use the physically verified selected research path.
    chosen_rel = Path(pair["original_freeze_path"])
    require(not chosen_rel.is_absolute() and ".." not in chosen_rel.parts and
            chosen_rel.parts[:2] == ("evidence", "football_research_freezes") and
            chosen_rel.name.startswith(fid + "_"),
            "SELECTED_FORECAST_PATH_UNSAFE")
    base = root / chosen_rel.parent
    options = sorted(p for p in base.glob(fid + "_*.json")
                     if "_result_" not in p.name)
    require(options, "NO_ORIGINAL_FORMULA_FREEZE_FOUND")
    candidates = []
    for p in options:
        doc, h = open_forecast(p)
        require(str(doc["provider_fixture_id"]) == fid and
                str(doc["provider_competition_id"]) == str(pair["competition_id"]) and
                stamp(doc["kickoff_utc"]) == kickoff,
                "ORIGINAL_FORMULA_EVENT_IDENTITY_CHANGED")
        frozen = stamp(doc["sealed_at_utc"])
        require(frozen < kickoff, "ORIGINAL_FORMULA_SNAPSHOT_AFTER_KICKOFF")
        prob = doc["research_probability_over25"]
        require(type(prob) in (int, float) and math.isfinite(prob) and 0 < prob < 1,
                "ORIGINAL_FORMULA_P_INVALID")
        candidates.append((frozen, p, doc, h))
    candidates.sort(key=lambda r: (r[0],r[1].as_posix()))
    first = candidates[0]
    selected_path = root / pair["original_freeze_path"]
    chosen = [x for x in candidates if x[1] == selected_path]
    require(len(chosen) == 1, "SELECTED_ORIGINAL_FREEZE_NOT_IN_ARCHIVE")
    selected = chosen[0]
    require(selected[3] == pair["original_freeze_sha256"] and
            selected[0] == stamp(pair["original_formula_research_frozen_at_utc"]),
            "LATEST_RESEARCH_FORECAST_SHA_OR_TIME_CHANGED")
    # Source and probability must be identical before equating two snapshots;
    # a later refit, revised historical response or changed prediction is
    # a genuine conflict, not an eligible paired observation.
    require(first[2]["source_snapshot_sha256"] ==
                selected[2]["source_snapshot_sha256"] ==
                pair["common_history_raw_sha256"],
            "FIRST_AND_RESEARCH_HISTORY_SHA_MISMATCH")
    require(math.isclose(first[2]["research_probability_over25"],
                         selected[2]["research_probability_over25"],
                         rel_tol=0.0, abs_tol=1e-12) and
            math.isclose(first[2]["research_probability_over25"],
                         pair["original_formula_research_p"],
                         rel_tol=0.0, abs_tol=1e-12),
            "FIRST_AND_RESEARCH_PROBABILITY_MISMATCH")
    return {
        "fixture_id": fid,
        "competition_id": str(pair["competition_id"]),
        "archive_immutable_original_snapshots": len(options),
        "earliest_forecast_path": first[1].relative_to(root).as_posix(),
        "earliest_forecast_file_sha256": first[3],
        "earliest_frozen_at_utc": first[0].isoformat(),
        "selected_research_forecast_path": selected[1].relative_to(root).as_posix(),
        "selected_research_forecast_file_sha256": selected[3],
        "selected_research_frozen_at_utc": selected[0].isoformat(),
        "distinct_files": first[3] != selected[3],
        "same_authenticated_source_history": True,
        "same_formula_probability": True,
        "p_original_formula_research": pair["original_formula_research_p"],
        "one_physical_fixture_count": 1,
        "no_future_outcome_used": True,
    }


def run(root: Path):
    manifest_bytes = (root / SOURCE).read_bytes()
    manifest = json.loads(manifest_bytes)
    pairs = validate_pairs_manifest(manifest)
    matched, rejected, seen = [], [], set()
    for pair in pairs:
        fid = str(pair["physical_event_id"])
        if fid in seen:
            rejected.append({"fixture_id": fid, "reason": "DUPLICATE_MANIFEST_EVENT"})
            continue
        seen.add(fid)
        try:
            matched.append(compare(root, pair))
        except (KeyError, ValueError, OSError, TypeError,
                json.JSONDecodeError) as exc:
            rejected.append({"fixture_id": fid, "reason": str(exc)[:140]})
    return {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_manifest_sha256": sha(manifest_bytes),
        "status": "PASS_SHA_BOUND_FIRST_TO_SELECTED_LINEAGE" if not rejected else
                  "FAIL_CLOSED_ORIGINAL_FORMULA_LINEAGE",
        "physical_fixture_count": len(pairs),
        "lineage_matched_fixture_count": len(matched),
        "lineage_rejected_fixture_count": len(rejected),
        "two_snapshot_fixture_count": sum(
            r["archive_immutable_original_snapshots"] == 2 for r in matched),
        "matched": matched,
        "rejected": rejected,
        "first_frozen_forecast_wins_settlement": True,
        "second_frozen_forecast_does_not_increment_observation_count": True,
        "source_order": ["SOFASCORE", "FLASHSCORE", "FOOTBALL_DATA_ORG"],
        "official_p_matrix_certified": False,
        "automatic_model_promotion": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    if {"notifications", "telegram", "tennis_signals",
        "daily_prematch_reports"} & set(args.out.parts):
        raise SystemExit("HISTORIC_LINEAGE_CANNOT_WRITE_SIGNALS")
    result = run(args.root)
    target = args.out if args.out.is_absolute() else args.root / args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        prev = json.loads(target.read_bytes())
        if ({k:v for k,v in prev.items() if k!="generated_at_utc"} ==
            {k:v for k,v in result.items() if k!="generated_at_utc"}):
            print(json.dumps({"unchanged":True,
                              "matched":result["lineage_matched_fixture_count"],
                              "rejected":result["lineage_rejected_fixture_count"]}))
            if result["rejected"]:
                raise SystemExit(2)
            return
    target.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n",
                      encoding="utf-8")
    print(json.dumps({"matched":result["lineage_matched_fixture_count"],
                      "rejected":result["lineage_rejected_fixture_count"],
                      "double_snapshots":result["two_snapshot_fixture_count"],
                      "real_money":"BLOCKED"},sort_keys=True))
    if result["rejected"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
