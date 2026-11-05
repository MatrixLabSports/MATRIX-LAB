"""Read-only synchronized discovery of ORIGINAL governed Over 2.5 candidates.

Runs immediately before the browser collector. It reuses the existing supervisor
discovery, but never executes the supervisor, sends Telegram, calls a provider, or
converts independent research probabilities to official p_matrix.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence/notifications/telegram/MATRIX_BROWSER_GOVERNED_INTAKE_LAST.json"
PROMOTION=ROOT/"evidence/api_football/governance/over_2_5_p_matrix_promotion.json"

def sha256(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build(now:datetime,root:Path=ROOT,discover=None)->dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("SYNCHRONIZER_REQUIRES_AWARE_UTC")
    now=now.astimezone(timezone.utc)
    day=now.astimezone(timezone(timedelta(hours=-5))).date()
    dates=[(day+timedelta(days=i)).isoformat() for i in (0,1)]
    path=root/"evidence/api_football/governance/over_2_5_p_matrix_promotion.json"
    try:
        promotion=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        promotion={}
    approved=(
        promotion.get("market")=="OVER_2_5" and
        promotion.get("promotion_status")=="PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY" and
        promotion.get("engine_executable_for_p_matrix") is True and
        promotion.get("promotion_scope")=="MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY" and
        (promotion.get("protections") or {}).get("real_money")=="BLOCKED" and
        (promotion.get("protections") or {}).get("automatic_wagering") is False
    )
    rows=[]
    discovered_candidate_count=0
    if approved:
        if discover is None:
            from tools.telegram_green_signal_alerts import discover_football
            discover=discover_football
        candidates=discover(dates)
        discovered_candidate_count=len(candidates)
        source_root=(root/"evidence/api_football/daily_prematch_reports").resolve()
        for c in candidates.values():
            if c.get("sport")!="football" or c.get("market_key")!="Goles totales Más/Menos" or c.get("selection_key")!="Más de 2.5":
                continue
            try:
                kickoff=datetime.fromisoformat(str(c["kickoff"]).replace("Z","+00:00"))
                p=float(c["p_matrix"])
                if kickoff.utcoffset() is None or not math.isfinite(p) or not (0.60<=p<1.0):
                    continue
                if not 0<(kickoff.astimezone(timezone.utc)-now).total_seconds()<=7200:
                    continue
                source=Path(str(c["source"]))
                source_path=(root/source).resolve() if not source.is_absolute() else source.resolve()
                if not source_path.is_relative_to(source_root) or not source_path.is_file():
                    continue
                relative=source_path.relative_to(root.resolve()).as_posix()
                if not c.get("fixture_id") or " vs " not in str(c.get("match") or ""):
                    continue
                rows.append({
                    "fixture_id":str(c["fixture_id"]),"match":str(c["match"]),
                    "kickoff":kickoff.astimezone(timezone.utc).isoformat(),
                    "p_matrix":p,"market":"OVER_2_5",
                    "source_path":relative,"source_sha256":sha256(source_path),
                    "research_only":False,"production_probability_authorized":True,
                    "telegram_signal_authorized":False
                })
            except (OSError,TypeError,ValueError,KeyError,OverflowError):
                continue
    rows.sort(key=lambda r:(r["kickoff"],r["fixture_id"]))
    return {
        "schema":"MATRIX_BROWSER_GOVERNED_INTAKE_SYNC_V1",
        "generated_at_utc":now.isoformat(),
        "status":("MODEL_PROMOTION_NOT_VERIFIED" if not approved else
                  "GOVERNED_CANDIDATES_FOUND" if rows else "NO_GOVERNED_CANONICAL_ROWS"),
        "market":"OVER_2_5","provenance":"ORIGINAL_GOVERNED_API_FOOTBALL_ONLY",
        "promotion_sha256":sha256(path) if approved else None,
        "original_p_matrix_only":True,"independent_provider_promotion":False,
        "candidates":rows,"candidate_count":len(rows),
        "upstream_discovered_candidate_count":discovered_candidate_count,
        "no_candidates_reason":(
            "ORIGINAL_PROMOTION_NOT_VERIFIED" if not approved else
            "ORIGINAL_SUPERVISOR_DISCOVERY_EMPTY" if discovered_candidate_count == 0 else
            "ORIGINAL_CANDIDATES_FAILED_SCOPE_OR_TIME_GATES" if not rows else None),
        "telegram_signal_authorized":False,"automatic_wagering":False,"real_money":"BLOCKED"
    }

def main()->None:
    if os.environ.get("REAL_MONEY")!="BLOCKED" or os.environ.get("AUTO_BETTING")!="DISABLED":
        raise SystemExit("MATRIX_CANONICAL_SYNC_SAFETY_GUARD")
    report=build(datetime.now(timezone.utc))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    os.replace(tmp,OUT)
    print(json.dumps({"status":report["status"],"candidate_count":report["candidate_count"],
                      "telegram_signal_authorized":False,"real_money":"BLOCKED"}))

if __name__=="__main__":
    main()
