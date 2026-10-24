from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SUSPECT_HOURS=36.0


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _load_jsonl(path:Path)->list[dict[str,Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _utc(value:object)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)


def exact_physical_key(row:Mapping[str,Any])->str:
    return "|".join([
        str(row.get("competition_id") or ""),
        str(row.get("season") or ""),
        str(row.get("home_team_id") or ""),
        str(row.get("away_team_id") or ""),
        str(row.get("kickoff_utc") or ""),
    ])


def pair_key(row:Mapping[str,Any])->str:
    return "|".join([
        str(row.get("competition_id") or ""),
        str(row.get("season") or ""),
        str(row.get("home_team_id") or ""),
        str(row.get("away_team_id") or ""),
    ])


def audit_football_physical_uniqueness(
    *,
    freeze:Mapping[str,Any],
    calibration_rows:list[Mapping[str,Any]]|None=None,
)->dict[str,Any]:
    rows=[
        row for row in freeze.get("rows",[]) or []
        if isinstance(row,Mapping)
    ]
    fixture_ids=[str(row.get("fixture_id") or "") for row in rows]
    duplicate_fixture_ids=sorted({
        fid for fid in fixture_ids if fid and fixture_ids.count(fid)>1
    })

    exact_groups:dict[str,list[Mapping[str,Any]]]=defaultdict(list)
    pair_groups:dict[str,list[Mapping[str,Any]]]=defaultdict(list)
    for row in rows:
        exact_groups[exact_physical_key(row)].append(row)
        pair_groups[pair_key(row)].append(row)

    exact_duplicates=[]
    for key,members in exact_groups.items():
        fixture_set={str(row.get("fixture_id") or "") for row in members}
        if len(members)>1 and len(fixture_set)>1:
            exact_duplicates.append({
                "physical_key":key,
                "fixture_ids":sorted(fixture_set),
                "count":len(members),
            })

    suspicious=[]
    for key,members in pair_groups.items():
        ordered=sorted(members,key=lambda row:_utc(row["kickoff_utc"]))
        for i,left in enumerate(ordered):
            for right in ordered[i+1:]:
                if str(left.get("fixture_id"))==str(right.get("fixture_id")):
                    continue
                delta=abs((_utc(right["kickoff_utc"])-_utc(left["kickoff_utc"])).total_seconds())/3600.0
                if delta<=SUSPECT_HOURS:
                    suspicious.append({
                        "pair_key":key,
                        "hours_apart":delta,
                        "fixture_a":str(left.get("fixture_id")),
                        "kickoff_a":left.get("kickoff_utc"),
                        "fixture_b":str(right.get("fixture_id")),
                        "kickoff_b":right.get("kickoff_utc"),
                    })

    calibration=list(calibration_rows or [])
    calibration_ids=[str(row.get("fixture_id") or "") for row in calibration]
    cal_dups=sorted({
        fid for fid in calibration_ids if fid and calibration_ids.count(fid)>1
    })
    freeze_ids=set(fixture_ids)
    cal_outside=sorted({fid for fid in calibration_ids if fid and fid not in freeze_ids})

    blockers=[]
    if duplicate_fixture_ids:
        blockers.append("DUPLICATE_FIXTURE_ID_IN_FREEZE")
    if exact_duplicates:
        blockers.append("DUPLICATE_PHYSICAL_EVENT_DIFFERENT_FIXTURE_ID")
    if suspicious:
        blockers.append("SUSPECT_SAME_TEAMS_WITHIN_36H")
    if cal_dups:
        blockers.append("DUPLICATE_FIXTURE_ID_IN_CALIBRATION_LEDGER")
    if cal_outside:
        blockers.append("CALIBRATION_EVENT_OUTSIDE_FREEZE")

    return {
        "schema":"MATRIX_FOOTBALL_PHYSICAL_UNIQUENESS_AUDIT_V1",
        "freeze_rows":len(rows),
        "unique_fixture_ids":len(set(fixture_ids)),
        "duplicate_fixture_id_groups":len(duplicate_fixture_ids),
        "exact_physical_duplicate_groups":len(exact_duplicates),
        "suspicious_same_pair_within_36h":len(suspicious),
        "calibration_rows":len(calibration),
        "calibration_unique_fixture_ids":len(set(calibration_ids)),
        "calibration_duplicate_fixture_ids":cal_dups,
        "calibration_outside_freeze":cal_outside,
        "exact_physical_duplicates":exact_duplicates,
        "suspicious_collisions":suspicious,
        "blockers":blockers,
        "result":"PASS" if not blockers else "FAIL",
        "p_matrix_status":"NOT_GENERATED",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--freeze",default="evidence/api_football/prospective_market_freeze/freeze.json")
    parser.add_argument("--calibration-ledger",default="evidence/api_football/prospective_calibration/ledger.jsonl")
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    report=audit_football_physical_uniqueness(
        freeze=_load(Path(args.freeze)),
        calibration_rows=_load_jsonl(Path(args.calibration_ledger)),
    )
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,sort_keys=True))
    if report["result"]!="PASS":
        raise SystemExit("FOOTBALL_PHYSICAL_UNIQUENESS_AUDIT_FAILED")


if __name__=="__main__":
    main()
