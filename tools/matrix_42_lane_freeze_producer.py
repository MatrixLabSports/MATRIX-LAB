from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from app.market.matrix_market_portfolio import ALL_MARKETS

ALLOWED={m.key for m in ALL_MARKETS}

def _aware(v:str)->datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_AWARE")
    return dt.astimezone(timezone.utc)

def build_freeze(*, market_lane:str, event_id:str, event_start_utc:str,
                 feature_snapshot:dict, source_artifacts:list[str],
                 generated_at_utc:str|None=None)->dict:
    if market_lane not in ALLOWED:
        raise ValueError("UNKNOWN_MARKET_LANE")
    if not event_id:
        raise ValueError("EVENT_ID_REQUIRED")
    start=_aware(event_start_utc)
    freeze=_aware(generated_at_utc) if generated_at_utc else datetime.now(timezone.utc)
    if freeze >= start:
        raise ValueError("FREEZE_NOT_BEFORE_EVENT_START")
    if not isinstance(feature_snapshot,dict) or not feature_snapshot:
        raise ValueError("FEATURE_SNAPSHOT_REQUIRED")
    if not source_artifacts:
        raise ValueError("SOURCE_ARTIFACT_REQUIRED")
    canonical=json.dumps(feature_snapshot,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    feature_sha=hashlib.sha256(canonical).hexdigest()
    obs=hashlib.sha256(f"{market_lane}|{event_id}|{freeze.isoformat()}|{feature_sha}".encode()).hexdigest()
    return {
      "record_type":"PROSPECTIVE_PREMATCH_FREEZE",
      "market_lane":market_lane,
      "event_id":str(event_id),
      "observation_key":obs,
      "freeze_timestamp_utc":freeze.replace(microsecond=0).isoformat(),
      "event_start_utc":start.replace(microsecond=0).isoformat(),
      "feature_snapshot_sha256":feature_sha,
      "feature_snapshot":feature_snapshot,
      "source_artifacts":source_artifacts,
      "target_outcome":None,
      "settlement":None,
      "odds_used_to_generate_probability":False,
      "missing_not_zero":True,
      "silent_imputation":False,
      "automatic_wagering":False,
      "real_money":"BLOCKED",
      "prospective_admitted":True,
      "counts_toward_100_300_600":True
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--market-lane",required=True)
    p.add_argument("--event-id",required=True)
    p.add_argument("--event-start-utc",required=True)
    p.add_argument("--features-json",required=True)
    p.add_argument("--source-artifact",action="append",required=True)
    p.add_argument("--out",default="evidence/market_portfolio/MATRIX_42_LANE_FREEZE_INBOX.jsonl")
    a=p.parse_args()
    features=json.loads(Path(a.features_json).read_text(encoding="utf-8"))
    row=build_freeze(market_lane=a.market_lane,event_id=a.event_id,event_start_utc=a.event_start_utc,
                     feature_snapshot=features,source_artifacts=a.source_artifact)
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("a",encoding="utf-8") as h:
        h.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({"status":"PASS","market_lane":a.market_lane,"observation_key":row["observation_key"]},sort_keys=True))

if __name__=="__main__":
    main()
