from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

HARD_DIR=Path("evidence/cor0203/holdout")
CLAY_OBS=Path("evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/prospective/observations.jsonl")
DEFAULT_INBOX=Path("evidence/market_portfolio/MATRIX_42_LANE_FREEZE_INBOX.jsonl")
DEFAULT_LEDGER=Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl")
DEFAULT_AUDIT=Path("evidence/market_portfolio/MATRIX_42_LANE_TENNIS_MATCH_WINNER_BRIDGE_LAST.json")


def _utc(value:object)->datetime:
    token=str(value or "").strip()
    if not token:
        raise ValueError("TIMESTAMP_MISSING")
    dt=datetime.fromisoformat(token.replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_AWARE")
    return dt.astimezone(timezone.utc)


def _sha(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def _read_jsonl(path:Path)->list[dict[str,Any]]:
    if not path.exists():
        return []
    out=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row=json.loads(line)
            if isinstance(row,dict):
                out.append(row)
    return out


def _hard_candidates(root:Path)->list[dict[str,Any]]:
    out=[]
    if not root.exists():
        return out
    for path in sorted(root.glob("MATRIX_COR0203_HOLDOUT_BATCH_*.json")):
        try:
            data=json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data,Mapping):
            continue
        if data.get("historical_backfill")!="FORBIDDEN":
            continue
        if int(data.get("outcomes_read") or 0)!=0:
            continue
        if data.get("real_money")!="BLOCKED":
            continue
        for row in data.get("observations") or []:
            if not isinstance(row,Mapping):
                continue
            item=dict(row)
            item["_source_path"]=path.as_posix()
            item["_source_batch_sha256"]=str(data.get("batch_sha256") or _sha(data))
            item["_source_kind"]="COR0203_HARD"
            out.append(item)
    return out


def _clay_candidates(path:Path)->list[dict[str,Any]]:
    out=[]
    for row in _read_jsonl(path):
        item=dict(row)
        item["_source_path"]=path.as_posix()
        item["_source_batch_sha256"]=_sha(row)
        item["_source_kind"]="CHALLENGER_CLAY"
        out.append(item)
    return out


def _normalize(row:Mapping[str,Any])->tuple[str,str,datetime,datetime,dict[str,Any],str]|None:
    kind=str(row.get("_source_kind") or "")
    event_id=str(row.get("event_id") or "").strip()
    if not event_id:
        return None
    start=_utc(row.get("event_start_utc"))
    freeze=_utc(row.get("freeze_at_utc"))
    if kind=="COR0203_HARD":
        if row.get("outcome") is not None or row.get("metrics_opened") is not False:
            return None
        elo=row.get("elo"); glicko=row.get("glicko")
        if not isinstance(elo,Mapping) or not isinstance(glicko,Mapping):
            return None
        prediction={
            "player_a":row.get("alphabetical_player_a"),
            "player_b":row.get("alphabetical_player_b"),
            "elo_p_player_a":float(elo["p_player_a"]),
            "glicko_p_player_a":float(glicko["p_player_a"]),
            "elo_model_id":elo.get("model_id"),
            "glicko_model_id":glicko.get("model_id"),
        }
        feature_sha=str(row.get("feature_snapshot_sha256") or "")
        if not feature_sha:
            return None
        physical=str(row.get("physical_event_key") or event_id)
        return event_id,physical,start,freeze,prediction,feature_sha
    if kind=="CHALLENGER_CLAY":
        if row.get("outcome") is not None or row.get("metrics_opened") is not False:
            return None
        if row.get("real_money")!="BLOCKED":
            return None
        model=row.get("model")
        if not isinstance(model,Mapping) or model.get("p_player_a") is None:
            return None
        prediction={
            "player_a":(row.get("player_a") or {}).get("canonical_name") if isinstance(row.get("player_a"),Mapping) else None,
            "player_b":(row.get("player_b") or {}).get("canonical_name") if isinstance(row.get("player_b"),Mapping) else None,
            "elo_p_player_a":float(model["p_player_a"]),
            "model_id":model.get("identity"),
        }
        feature_sha=str(row.get("observation_sha256") or "")
        if not feature_sha:
            return None
        physical=str(row.get("physical_event_key") or event_id)
        return event_id,physical,start,freeze,prediction,feature_sha
    return None


def build_rows(*,hard_dir:Path,clay_obs:Path,now_utc:datetime,existing_keys:set[str])->tuple[list[dict[str,Any]],dict[str,Any]]:
    candidates=_hard_candidates(hard_dir)+_clay_candidates(clay_obs)
    admitted=[]; blocked=[]; seen_physical=set()
    for raw in candidates:
        try:
            norm=_normalize(raw)
        except Exception as exc:
            blocked.append({"event_id":raw.get("event_id"),"reason":"NORMALIZE_FAILED:"+type(exc).__name__})
            continue
        if norm is None:
            continue
        event_id,physical,start,freeze,prediction,feature_sha=norm
        if start<=now_utc:
            continue
        if freeze>=start:
            blocked.append({"event_id":event_id,"reason":"FREEZE_NOT_PREMATCH"})
            continue
        if physical in seen_physical:
            continue
        obs_key=f"tennis|MATCH_WINNER|event:{physical}|freeze:{freeze.isoformat()}"
        if obs_key in existing_keys:
            seen_physical.add(physical)
            continue
        admitted.append({
            "observation_key":obs_key,
            "record_type":"PROSPECTIVE_PREMATCH_FREEZE",
            "sport":"tennis",
            "market_lane":"MATCH_WINNER",
            "event_id":event_id,
            "physical_event_key":physical,
            "event_start_utc":start.isoformat(),
            "freeze_timestamp_utc":freeze.isoformat(),
            "source_kind":raw.get("_source_kind"),
            "source_path":raw.get("_source_path"),
            "source_snapshot_sha256":str(raw.get("_source_batch_sha256") or _sha(raw)),
            "feature_snapshot_sha256":feature_sha,
            "prediction_snapshot_sha256":_sha({"event_id":event_id,"prediction":prediction,"feature_snapshot_sha256":feature_sha}),
            "prediction":prediction,
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
        seen_physical.add(physical)
    admitted.sort(key=lambda x:(x["event_start_utc"],x["physical_event_key"]))
    audit={
        "schema":"MATRIX_42_LANE_TENNIS_MATCH_WINNER_BRIDGE_V1",
        "generated_at_utc":now_utc.replace(microsecond=0).isoformat(),
        "hard_candidate_rows_scanned":len(_hard_candidates(hard_dir)),
        "clay_candidate_rows_scanned":len(_clay_candidates(clay_obs)),
        "eligible_future_unique_events":len(admitted),
        "eligible_future_lane_rows":len(admitted),
        "blocked_count":len(blocked),
        "blocked":blocked[:100],
        "protections":{
            "only_currently_future_events_admitted":True,
            "historical_backfill_forbidden":True,
            "freeze_strictly_before_start":True,
            "outcomes_read":0,
            "metrics_opened":False,
            "odds_used_to_generate_probability":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "status":"PASS",
    }
    return admitted,audit


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--hard-dir",default=str(HARD_DIR))
    p.add_argument("--clay-observations",default=str(CLAY_OBS))
    p.add_argument("--inbox",default=str(DEFAULT_INBOX))
    p.add_argument("--ledger",default=str(DEFAULT_LEDGER))
    p.add_argument("--audit-out",default=str(DEFAULT_AUDIT))
    a=p.parse_args()
    inbox=Path(a.inbox)
    existing={str(x.get("observation_key") or "") for x in _read_jsonl(inbox)+_read_jsonl(Path(a.ledger))}
    rows,audit=build_rows(hard_dir=Path(a.hard_dir),clay_obs=Path(a.clay_observations),now_utc=datetime.now(timezone.utc).replace(microsecond=0),existing_keys=existing)
    if rows:
        inbox.parent.mkdir(parents=True,exist_ok=True)
        with inbox.open("a",encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
    out=Path(a.audit_out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(audit,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":audit["status"],"eligible_future_unique_events":audit["eligible_future_unique_events"],"hard_scanned":audit["hard_candidate_rows_scanned"],"clay_scanned":audit["clay_candidate_rows_scanned"],"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
