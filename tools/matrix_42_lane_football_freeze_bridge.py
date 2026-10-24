from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SOURCE_FREEZE = Path("evidence/api_football/prospective_market_freeze/freeze.json")
DEFAULT_INBOX = Path("evidence/market_portfolio/MATRIX_42_LANE_FREEZE_INBOX.jsonl")
DEFAULT_LEDGER = Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl")
DEFAULT_AUDIT = Path("evidence/market_portfolio/MATRIX_42_LANE_FOOTBALL_FREEZE_BRIDGE_LAST.json")

LANES = (
    "MATCH_RESULT_1X2",
    "DOUBLE_CHANCE_1X",
    "DOUBLE_CHANCE_X2",
    "DOUBLE_CHANCE_12",
    "TOTAL_GOALS_OVER_UNDER",
)


def _load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row=json.loads(line)
            if isinstance(row,dict):
                out.append(row)
    return out


def _utc(value: object) -> datetime:
    token=str(value or "").strip()
    if not token:
        raise ValueError("TIMESTAMP_MISSING")
    dt=datetime.fromisoformat(token.replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_AWARE")
    return dt.astimezone(timezone.utc)


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _predictions(row: Mapping[str,Any]) -> dict[str,Any]:
    frozen=row.get("frozen_research_probabilities")
    if not isinstance(frozen,Mapping):
        raise ValueError("FROZEN_RESEARCH_PROBABILITIES_MISSING")
    one=frozen.get("1x2")
    if not isinstance(one,Mapping):
        raise ValueError("FROZEN_1X2_MISSING")
    h=float(one["H"]); d=float(one["D"]); a=float(one["A"])
    over=float(frozen["over_2_5"])
    vals=[h,d,a,over,h+d,d+a,h+a]
    if any((x < 0.0 or x > 1.0) for x in vals):
        raise ValueError("PROBABILITY_OUT_OF_RANGE")
    if abs((h+d+a)-1.0)>1e-6:
        raise ValueError("1X2_NOT_NORMALIZED")
    return {
        "MATCH_RESULT_1X2":{"H":h,"D":d,"A":a},
        "DOUBLE_CHANCE_1X":{"1X":h+d},
        "DOUBLE_CHANCE_X2":{"X2":d+a},
        "DOUBLE_CHANCE_12":{"12":h+a},
        "TOTAL_GOALS_OVER_UNDER":{"over_2_5":over,"under_2_5":1.0-over},
    }


def build_rows(
    source: Mapping[str,Any],
    *,
    now_utc: datetime,
    existing_keys: set[str],
) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    protections=source.get("protections") or {}
    required={
        "future_only":True,
        "freeze_strictly_before_kickoff":True,
        "missing_feature_imputation":False,
        "outcomes_read_at_freeze":False,
        "odds_used_to_generate_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    for key,val in required.items():
        if protections.get(key)!=val:
            raise ValueError("SOURCE_PROTECTION_INVALID:"+key)

    admitted=[]
    blocked=[]
    rows=source.get("rows") or []
    for src in rows:
        if not isinstance(src,Mapping):
            continue
        fid=str(src.get("fixture_id") or "").strip()
        try:
            start=_utc(src.get("kickoff_utc"))
            freeze=_utc(src.get("freeze_at_utc"))
        except ValueError as exc:
            blocked.append({"fixture_id":fid or None,"reason":str(exc)})
            continue
        if freeze>=start:
            blocked.append({"fixture_id":fid,"reason":"SOURCE_FREEZE_NOT_PREMATCH"})
            continue
        if start<=now_utc:
            continue
        if src.get("outcome") is not None:
            blocked.append({"fixture_id":fid,"reason":"SOURCE_OUTCOME_PRESENT"})
            continue
        if src.get("settlement_status") not in {None,"PENDING_FINAL"}:
            blocked.append({"fixture_id":fid,"reason":"SOURCE_SETTLEMENT_NOT_PENDING"})
            continue
        try:
            predictions=_predictions(src)
        except (KeyError,TypeError,ValueError) as exc:
            blocked.append({"fixture_id":fid,"reason":"PREDICTION_INVALID:"+str(exc)})
            continue

        source_snapshot_sha=_sha(dict(src))
        for lane in LANES:
            key=f"football|{lane}|fixture:{fid}|freeze:{freeze.isoformat()}"
            if key in existing_keys:
                continue
            prediction=predictions[lane]
            admitted.append({
                "observation_key":key,
                "record_type":"PROSPECTIVE_PREMATCH_FREEZE",
                "sport":"football",
                "market_lane":lane,
                "fixture_id":fid,
                "event_id":fid,
                "event_start_utc":start.isoformat(),
                "freeze_timestamp_utc":freeze.isoformat(),
                "source_schema":source.get("schema"),
                "source_snapshot_sha256":source_snapshot_sha,
                "prediction_snapshot_sha256":_sha({
                    "fixture_id":fid,
                    "lane":lane,
                    "prediction":prediction,
                    "freeze_timestamp_utc":freeze.isoformat(),
                }),
                "prediction":prediction,
                "model_basis":"EXISTING_FROZEN_RESEARCH_PROBABILITIES",
                "derived_from_1x2": lane in {
                    "DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2","DOUBLE_CHANCE_12"
                },
                "target_outcome":None,
                "settlement":None,
                "prospective_admitted":True,
                "counts_toward_100_300_600":True,
                "odds_used_to_generate_probability":False,
                "missing_not_zero":True,
                "silent_imputation":False,
                "automatic_wagering":False,
                "real_money":"BLOCKED",
            })

    admitted.sort(key=lambda x:(x["event_start_utc"],x["fixture_id"],x["market_lane"]))
    audit={
        "schema":"MATRIX_42_LANE_FOOTBALL_FREEZE_BRIDGE_V1",
        "generated_at_utc":now_utc.replace(microsecond=0).isoformat(),
        "source_schema":source.get("schema"),
        "source_frozen_event_count":source.get("frozen_event_count"),
        "source_freeze_sha256":_sha(source),
        "eligible_future_lane_rows":len(admitted),
        "eligible_future_unique_fixtures":len({x["fixture_id"] for x in admitted}),
        "lanes_emitted":list(LANES),
        "blocked_count":len(blocked),
        "blocked":blocked[:100],
        "protections":{
            "source_probabilities_reused_without_refit":True,
            "double_chance_is_exact_sum_of_frozen_1x2":True,
            "post_start_backfill_forbidden":True,
            "outcomes_read":0,
            "odds_used_to_generate_probability":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "status":"PASS",
    }
    return admitted,audit


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--source",default=str(SOURCE_FREEZE))
    p.add_argument("--inbox",default=str(DEFAULT_INBOX))
    p.add_argument("--ledger",default=str(DEFAULT_LEDGER))
    p.add_argument("--audit-out",default=str(DEFAULT_AUDIT))
    a=p.parse_args()

    source=_load(Path(a.source))
    existing={str(x.get("observation_key") or "") for x in _read_jsonl(Path(a.ledger))}
    now=datetime.now(timezone.utc).replace(microsecond=0)
    rows,audit=build_rows(source,now_utc=now,existing_keys=existing)

    inbox=Path(a.inbox); inbox.parent.mkdir(parents=True,exist_ok=True)
    inbox.write_text(
        "".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in rows),
        encoding="utf-8",
    )
    out=Path(a.audit_out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(audit,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":audit["status"],
        "eligible_future_lane_rows":audit["eligible_future_lane_rows"],
        "eligible_future_unique_fixtures":audit["eligible_future_unique_fixtures"],
        "lanes_emitted":audit["lanes_emitted"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
