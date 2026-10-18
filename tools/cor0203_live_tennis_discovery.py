from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.cor0203_physical_identity import physical_event_key


def canonical_sha(value: Any) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_utc(value: str) -> datetime:
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--reconciliation", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--as-of-utc")
    args=parser.parse_args()

    coverage=json.loads(Path(args.coverage).read_text(encoding="utf-8"))
    reconciliation=json.loads(Path(args.reconciliation).read_text(encoding="utf-8"))
    as_of=parse_utc(args.as_of_utc or reconciliation.get("generated_at_utc") or coverage.get("generated_at_utc") or datetime.now(timezone.utc).isoformat())
    source_sha=canonical_sha(coverage)

    provider=(coverage.get("providers") or {}).get("live_tennis_api") or {}
    provider_rows={int(x.get("provider_match_id")):x for x in (provider.get("d0_d2_hard_candidates") or []) if isinstance(x,dict) and isinstance(x.get("provider_match_id"),int)}
    rows=[]
    for rec in reconciliation.get("records",[]) or []:
        if not isinstance(rec,dict) or rec.get("status")!="NEW_FUTURE_GAP_VERIFIED":
            continue
        mid=rec.get("provider_match_id")
        raw=provider_rows.get(int(mid)) if isinstance(mid,int) else None
        if not isinstance(raw,dict):
            continue
        merged=dict(raw)
        names=list(rec.get("canonical_names") or [])
        if len(names)==2:
            merged["player1_name"]=names[0]
            merged["player2_name"]=names[1]
        merged["competition_override"]=rec.get("competition")
        merged["round_override"]=rec.get("round")
        merged["reconciliation_status"]=rec.get("status")
        merged["independent_validation"]=rec.get("independent_validation")
        rows.append(merged)

    eligible=[]
    rejected=[]
    for row in rows:
        mid=row.get("provider_match_id")
        start_raw=str(row.get("start_time_utc") or "")
        p1id=row.get("player1_id")
        p2id=row.get("player2_id")
        p1=str(row.get("player1_name") or "").strip()
        p2=str(row.get("player2_name") or "").strip()
        blockers=[]
        try:
            start=parse_utc(start_raw)
        except Exception:
            start=None
            blockers.append("EVENT_START_INVALID")
        if start is not None and start <= as_of:
            blockers.append("EVENT_NOT_FUTURE")
        if not isinstance(mid,int) or mid <= 0:
            blockers.append("PROVIDER_EVENT_ID_INVALID")
        if not isinstance(p1id,int) or not isinstance(p2id,int) or p1id<=0 or p2id<=0:
            blockers.append("PROVIDER_PLAYER_ID_INVALID")
        if not p1 or not p2 or p1==p2:
            blockers.append("PLAYER_IDENTITY_INVALID")
        if str(row.get("surface") or "").strip().casefold() != "hard":
            blockers.append("SURFACE_NOT_HARD")
        if str(row.get("tour") or "").strip().casefold() != "challenger":
            blockers.append("TOUR_NOT_CHALLENGER")
        if str(row.get("round_code") or "") not in {"R128","R64","R32","R16","QF","SF","F"}:
            blockers.append("ROUND_NOT_MAIN_SINGLES_STAGE")

        if blockers:
            rejected.append({"provider_match_id":mid,"blockers":sorted(set(blockers))})
            continue

        event={
            "event_id":f"live-tennis-api:match:{mid}",
            "canonical_source_event_id":f"live-tennis-api:match:{mid}",
            "competition":str(row.get("competition_override") or ("Wuning 3 Challenger" if "Wuning 3" in str(row.get("tournament") or "") else row.get("tournament") or "")),
            "competition_id":None,
            "round":str(row.get("round_override") or row.get("round_code") or row.get("round") or ""),
            "surface":"Hard",
            "tour_level":"C",
            "target_period":20260921,
            "event_start_utc":start.isoformat(),
            "source_provider":"live_tennis_api",
            "source_reference":f"{args.coverage};reconciliation={args.reconciliation};match_id={mid};raw_tournament={row.get('tournament')};round={row.get('round')};independent_validation={row.get('independent_validation')}",
            "source_snapshot_sha256":source_sha,
            "players":[
                {
                    "name":p1,
                    "provider_player_id":f"live-tennis-api:player:{p1id}",
                    "provider_ranking":None
                },
                {
                    "name":p2,
                    "provider_player_id":f"live-tennis-api:player:{p2id}",
                    "provider_ranking":None
                }
            ],
            "player_identities":[
                {"display_name":p1,"provider":"live_tennis_api","provider_player_id":f"live-tennis-api:player:{p1id}"},
                {"display_name":p2,"provider":"live_tennis_api","provider_player_id":f"live-tennis-api:player:{p2id}"}
            ],
            "historical_identity_crosswalk_status":"PENDING"
        }
        event["physical_event_key"]=physical_event_key(event)
        eligible.append(event)

    payload={
        "schema":"MATRIX_COR0203_LIVE_TENNIS_API_DISCOVERY_V1",
        "provider":"live_tennis_api",
        "status":"DISCOVERY_COMPLETED",
        "as_of_utc":as_of.isoformat(),
        "source_coverage_path":args.coverage,
        "source_coverage_sha256":source_sha,
        "reconciliation_path":args.reconciliation,
        "input_verified_future_gaps":len(rows),
        "eligible_candidates":eligible,
        "provider_rejected":rejected,
        "automatic_model_feed":False,
        "governed_preregistration_required":True,
        "metrics_opened":False,
        "outcomes_read":0,
        "odds_used":False,
        "real_money":"BLOCKED"
    }
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":payload["status"],
        "eligible":len(eligible),
        "rejected":len(rejected),
        "eligible_ids":[x["event_id"] for x in eligible]
    },sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
