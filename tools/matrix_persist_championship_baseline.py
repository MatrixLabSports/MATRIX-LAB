"""Persist ONLY evidence of independent historical baseline replay in research branch."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path

BRANCH="repair/cor09-world-pipeline"

def git(*args,allowed=(0,)):
    r=subprocess.run(["git",*args],capture_output=True,text=True,check=False)
    if r.returncode not in allowed:
        raise RuntimeError(f"BASELINE_EVIDENCE_GIT_{args[0]}_FAILED_{r.returncode}")
    return r.returncode

def main():
    run=os.environ.get("GITHUB_RUN_ID","").strip()
    if not run.isdigit():raise ValueError("BASELINE_EVIDENCE_RUN_ID_MISSING")
    p=Path("evidence/football_world_inventory/2026-11-03")/f"MATRIX_CHAMPIONSHIP_OVER25_BASELINE_WINDOWS_{run}.json"
    d=json.loads(p.read_text(encoding="utf-8"))
    if (d.get("schema")!="MATRIX_CHAMPIONSHIP_ORIGINAL_FROZEN_BASELINE_REPLAY_V1"
        or d.get("real_money")!="BLOCKED"
        or d.get("automatic_wagering") is not False
        or d.get("telegram_signal_authorized") is not False
        or d.get("production_p_matrix_authorized") is not False
        or d.get("calibrated_model_equivalence_verified") is not False
        or any(row.get("production_p_matrix_authorized") is not False
               for row in d.get("rows",[]))):
        raise ValueError("BASELINE_EVIDENCE_GOVERNANCE_INVALID")
    cross=Path("evidence/football_world_inventory/2026-11-03")/f"MATRIX_CHAMPIONSHIP_CROSS_PROVIDER_WINDOWS_{run}.json"
    x=json.loads(cross.read_text(encoding="utf-8"))
    if (x.get("schema")!="MATRIX_CHAMPIONSHIP_HISTORICAL_CROSS_PROVIDER_HTTP_REPLAY_V1"
        or x.get("real_money")!="BLOCKED"
        or x.get("automatic_wagering") is not False
        or x.get("telegram_signal_authorized") is not False
        or x.get("new_production_p_matrix_authorized") is not False
        or x.get("full_original_calibrated_model_equivalence_verified") is not False
        or x.get("network_calls")!=0):
        raise ValueError("CROSS_PROVIDER_EVIDENCE_GOVERNANCE_INVALID")
    bridge=Path("evidence/football_world_inventory/2026-11-03")/f"MATRIX_CHAMPIONSHIP_ENRICHED_BRIDGE_WINDOWS_{run}.json"
    e=json.loads(bridge.read_text(encoding="utf-8"))
    if (e.get("schema")!="MATRIX_CHAMPIONSHIP_ENRICHED_PROVIDER_HISTORICAL_BRIDGE_V1"
        or e.get("real_money")!="BLOCKED"
        or e.get("network_calls")!=0
        or e.get("automatic_wagering") is not False
        or e.get("telegram_signal_authorized") is not False
        or e.get("production_p_matrix_authorized") is not False
        or e.get("prospective_enriched_provider_equivalence_verified") is not False
        or e.get("original_canonical_targets")!=11
        or e.get("historical_three_way_parity_count",0)+e.get("blocked_count",0)!=11):
        raise ValueError("ENRICHED_BRIDGE_EVIDENCE_GOVERNANCE_INVALID")
    git("config","user.name","matrix-baseline-audit")
    git("config","user.email","matrix-baseline-audit@users.noreply.github.com")
    git("add","--",p.as_posix(),cross.as_posix(),bridge.as_posix())
    if git("diff","--cached","--quiet",allowed=(0,1))==0:
        print("BASELINE_EVIDENCE_UNCHANGED");return
    git("commit","-m","evidence(over25): independently verify authentic Championship group baseline")
    for _ in range(4):
        git("fetch","origin",BRANCH)
        git("rebase",f"origin/{BRANCH}")
        r=subprocess.run(["git","push","origin",f"HEAD:{BRANCH}"],capture_output=True,text=True,check=False)
        if r.returncode==0:
            print("BASELINE_EVIDENCE_PERSISTED")
            return
    raise RuntimeError("BASELINE_EVIDENCE_PUSH_FAILED")
if __name__=="__main__":
    main()
