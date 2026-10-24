from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.api_football_period_goals_lab import (
    _expected_period_goals,
    _load_group,
    _poisson_over,
)

SOURCE_FREEZE = Path("evidence/api_football/prospective_market_freeze/freeze.json")
DEFAULT_INBOX = Path("evidence/market_portfolio/MATRIX_42_LANE_FREEZE_INBOX.jsonl")
DEFAULT_LEDGER = Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl")
DEFAULT_AUDIT = Path("evidence/market_portfolio/MATRIX_42_LANE_PERIOD_GOALS_FREEZE_BRIDGE_LAST.json")

LANES = (
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
    "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
)


def _load(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str,Any]]:
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


def _sha(value: Any)->str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _predictions(fhl:float,fal:float,shl:float,sal:float)->dict[str,Any]:
    return {
        "FIRST_HALF_TOTAL_GOALS_OVER_UNDER":{
            "over_0_5":_poisson_over(fhl+fal,0.5),
            "under_0_5":1.0-_poisson_over(fhl+fal,0.5),
            "over_1_5":_poisson_over(fhl+fal,1.5),
            "under_1_5":1.0-_poisson_over(fhl+fal,1.5),
        },
        "SECOND_HALF_TOTAL_GOALS_OVER_UNDER":{
            "over_0_5":_poisson_over(shl+sal,0.5),
            "under_0_5":1.0-_poisson_over(shl+sal,0.5),
            "over_1_5":_poisson_over(shl+sal,1.5),
            "under_1_5":1.0-_poisson_over(shl+sal,1.5),
        },
        "FIRST_HALF_TEAM_TOTAL_GOALS_HOME":{
            "over_0_5":_poisson_over(fhl,0.5),
            "under_0_5":1.0-_poisson_over(fhl,0.5),
        },
        "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY":{
            "over_0_5":_poisson_over(fal,0.5),
            "under_0_5":1.0-_poisson_over(fal,0.5),
        },
        "SECOND_HALF_TEAM_TOTAL_GOALS_HOME":{
            "over_0_5":_poisson_over(shl,0.5),
            "under_0_5":1.0-_poisson_over(shl,0.5),
        },
        "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY":{
            "over_0_5":_poisson_over(sal,0.5),
            "under_0_5":1.0-_poisson_over(sal,0.5),
        },
    }


def build_rows(
    source:Mapping[str,Any],
    *,
    repo_root:Path,
    now_utc:datetime,
    existing_keys:set[str],
)->tuple[list[dict[str,Any]],dict[str,Any]]:
    protections=source.get("protections") or {}
    if protections.get("freeze_strictly_before_kickoff") is not True:
        raise ValueError("SOURCE_FREEZE_PROTECTION_INVALID")
    if protections.get("outcomes_read_at_freeze") is not False:
        raise ValueError("SOURCE_OUTCOME_PROTECTION_INVALID")
    if protections.get("odds_used_to_generate_probability") is not False:
        raise ValueError("SOURCE_ODDS_PROTECTION_INVALID")
    if protections.get("real_money")!="BLOCKED":
        raise ValueError("SOURCE_REAL_MONEY_INVALID")

    admitted=[]; blocked=[]
    cache:dict[str,tuple[list[dict[str,Any]],str]]={}
    future_candidates=0
    for src in source.get("rows") or []:
        if not isinstance(src,Mapping):
            continue
        fid=str(src.get("fixture_id") or "")
        try:
            start=_utc(src.get("kickoff_utc")); freeze=_utc(src.get("freeze_at_utc"))
        except ValueError as exc:
            blocked.append({"fixture_id":fid,"reason":str(exc)}); continue
        if start<=now_utc:
            continue
        future_candidates+=1
        if freeze>=start:
            blocked.append({"fixture_id":fid,"reason":"SOURCE_FREEZE_NOT_PREMATCH"}); continue
        if src.get("outcome") is not None:
            blocked.append({"fixture_id":fid,"reason":"SOURCE_OUTCOME_PRESENT"}); continue

        rel=str(src.get("historical_baseline_source") or "").strip()
        path=(repo_root/rel) if rel else None
        if path is None or not path.exists():
            blocked.append({"fixture_id":fid,"reason":"PERIOD_HISTORY_SOURCE_MISSING","source":rel or None}); continue
        key=path.as_posix()
        try:
            if key not in cache:
                cache[key]=_load_group(path)
            group,digest=cache[key]
        except Exception as exc:
            blocked.append({"fixture_id":fid,"reason":"PERIOD_HISTORY_LOAD_FAILED:"+type(exc).__name__}); continue

        prior=[r for r in group if r["kickoff_utc"]<freeze]
        try:
            first=_expected_period_goals(prior,str(src.get("home_team_id") or ""),str(src.get("away_team_id") or ""),"first_half")
            second=_expected_period_goals(prior,str(src.get("home_team_id") or ""),str(src.get("away_team_id") or ""),"second_half")
        except Exception as exc:
            blocked.append({"fixture_id":fid,"reason":"PERIOD_FEATURE_BUILD_FAILED:"+type(exc).__name__}); continue
        if first is None or second is None:
            blocked.append({"fixture_id":fid,"reason":"INSUFFICIENT_STRICTLY_PRIOR_TEAM_PERIOD_HISTORY"}); continue
        fhl,fal=first; shl,sal=second
        feature_snapshot={
            "fixture_id":fid,
            "freeze_timestamp_utc":freeze.isoformat(),
            "history_source":rel,
            "history_source_sha256":digest,
            "prior_group_fixture_count":len(prior),
            "expected_first_half_goals":{"home":fhl,"away":fal},
            "expected_second_half_goals":{"home":shl,"away":sal},
            "model":"PERIOD_TEAM_POISSON_PIT_V1",
        }
        feature_sha=_sha(feature_snapshot)
        preds=_predictions(fhl,fal,shl,sal)
        for lane,prediction in preds.items():
            obs_key=f"football|{lane}|fixture:{fid}|freeze:{freeze.isoformat()}"
            if obs_key in existing_keys:
                continue
            admitted.append({
                "observation_key":obs_key,
                "record_type":"PROSPECTIVE_PREMATCH_FREEZE",
                "sport":"football",
                "market_lane":lane,
                "fixture_id":fid,
                "event_id":fid,
                "event_start_utc":start.isoformat(),
                "freeze_timestamp_utc":freeze.isoformat(),
                "source_schema":source.get("schema"),
                "source_snapshot_sha256":_sha(dict(src)),
                "feature_snapshot_sha256":feature_sha,
                "prediction_snapshot_sha256":_sha({"lane":lane,"prediction":prediction,"feature_snapshot_sha256":feature_sha}),
                "prediction":prediction,
                "model_basis":"PERIOD_TEAM_POISSON_PIT_V1_STRICTLY_PRIOR_HISTORY",
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
        "schema":"MATRIX_42_LANE_PERIOD_GOALS_FREEZE_BRIDGE_V1",
        "generated_at_utc":now_utc.replace(microsecond=0).isoformat(),
        "source_schema":source.get("schema"),
        "future_source_fixture_candidates":future_candidates,
        "eligible_future_unique_fixtures":len({x["fixture_id"] for x in admitted}),
        "eligible_future_lane_rows":len(admitted),
        "lanes_emitted":list(LANES),
        "blocked_count":len(blocked),
        "blocked_reason_counts":{},
        "blocked":blocked[:100],
        "protections":{
            "strictly_prior_kickoff_history_only":True,
            "source_probabilities_not_used_for_period_model":True,
            "parameter_refit":False,
            "parameter_search":False,
            "post_start_backfill_forbidden":True,
            "outcomes_read":0,
            "odds_used_to_generate_probability":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "status":"PASS",
    }
    for row in blocked:
        reason=row["reason"]
        audit["blocked_reason_counts"][reason]=audit["blocked_reason_counts"].get(reason,0)+1
    return admitted,audit


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--source",default=str(SOURCE_FREEZE))
    p.add_argument("--inbox",default=str(DEFAULT_INBOX))
    p.add_argument("--ledger",default=str(DEFAULT_LEDGER))
    p.add_argument("--audit-out",default=str(DEFAULT_AUDIT))
    a=p.parse_args()

    source=_load(Path(a.source))
    inbox=Path(a.inbox)
    current=_read_jsonl(inbox)
    ledger=_read_jsonl(Path(a.ledger))
    existing_keys={str(x.get("observation_key") or "") for x in current+ledger}
    rows,audit=build_rows(source,repo_root=Path("."),now_utc=datetime.now(timezone.utc).replace(microsecond=0),existing_keys=existing_keys)
    if rows:
        inbox.parent.mkdir(parents=True,exist_ok=True)
        with inbox.open("a",encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
    out=Path(a.audit_out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(audit,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":audit["status"],
        "future_source_fixture_candidates":audit["future_source_fixture_candidates"],
        "eligible_future_unique_fixtures":audit["eligible_future_unique_fixtures"],
        "eligible_future_lane_rows":audit["eligible_future_lane_rows"],
        "blocked_count":audit["blocked_count"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
