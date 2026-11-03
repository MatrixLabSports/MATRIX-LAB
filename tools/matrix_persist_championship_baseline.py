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
    git("config","user.name","matrix-baseline-audit")
    git("config","user.email","matrix-baseline-audit@users.noreply.github.com")
    git("add","--",p.as_posix())
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
