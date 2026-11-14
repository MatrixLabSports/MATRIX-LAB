from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

def _load(p: Path)->dict[str,Any]:
    d=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(d,dict): raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return d

def build(root: Path)->dict[str,Any]:
    m=_load(root/"evidence/api_football/challenger/challenger_manifest.json")
    h=_load(root/"evidence/api_football/challenger/final_holdout_adjudication.json")
    if h["holdout_seal_sha256_verified"]!=m["holdout_seal_sha256"]:
        raise ValueError("HOLDOUT_SEAL_MISMATCH")
    rows=[]
    for market in ("1x2","over_2_5","btts"):
        hm=h["metrics"][market]
        passed=bool(hm["market_superiority"])
        rows.append({
            "market":market,
            "challenger_name":m["challenger_name"],
            "frozen_parameters":m["frozen_parameters"][market],
            "final_holdout_sample_size":hm["challenger"]["sample_size"],
            "final_holdout_challenger_metrics":hm["challenger"],
            "final_holdout_poisson_metrics":hm["poisson"],
            "market_holdout_gate_passed":passed,
            "market_governance_status":"MARKET_CHALLENGER_FROZEN_APPROVED_FOR_NEXT_GATES" if passed else "MARKET_CHALLENGER_REJECTED",
            "engine_executable_for_p_matrix":False,
        })
    return {
        "schema":"MATRIX_FOOTBALL_MARKET_GOVERNANCE_V1",
        "created_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_final_holdout_status":h["final_holdout_status"],
        "holdout_seal_sha256":m["holdout_seal_sha256"],
        "markets":rows,
        "approved_markets":[r["market"] for r in rows if r["market_holdout_gate_passed"]],
        "rejected_markets":[r["market"] for r in rows if not r["market_holdout_gate_passed"]],
        "p_matrix_generated":False,
        "governed_engine_promoted":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }

def main()->None:
    root=Path(".")
    d=build(root)
    out=root/"evidence/api_football/market_governance"
    out.mkdir(parents=True,exist_ok=True)
    (out/"market_governance.json").write_text(json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"approved_markets":d["approved_markets"],"rejected_markets":d["rejected_markets"],"real_money":d["real_money"]},sort_keys=True))
if __name__=="__main__": main()
