"""Preserve one authentic run-scoped football PIT bundle; research only."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from tools.matrix_championship_atomic_pit_cycle import unpack

BRANCH="repair/cor09-world-pipeline"

def git(*args,ok=(0,)):
    r=subprocess.run(["git",*args],capture_output=True,text=True,check=False)
    if r.returncode not in ok:
        raise RuntimeError(f"ATOMIC_PIT_GIT_{args[0]}_FAILED_{r.returncode}")
    return r.returncode

def main():
    run=os.environ.get("GITHUB_RUN_ID","")
    if not run.isdigit():
        raise ValueError("ATOMIC_PIT_BAD_RUN_ID")
    day=os.environ.get("MATRIX_TARGET_BOGOTA_DATE","2026-11-03")
    p=Path("evidence/football_world_inventory")/day/f"MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_{run}.json"
    bundle=json.loads(p.read_text(encoding="utf-8"))
    unpack(bundle)
    if (bundle["run_id"]!=run or bundle["target_date_bogota"]!=day
        or bundle["production_probability_authorized"] is not False
        or bundle["telegram_signal_authorized"] is not False
        or bundle["automatic_wagering"] is not False
        or bundle["real_money"]!="BLOCKED"):
        raise ValueError("ATOMIC_PIT_UNSAFE_PERSISTENCE")
    git("config","user.name","matrix-atomic-pit-research")
    git("config","user.email","matrix-atomic-pit-research@users.noreply.github.com")
    git("add","--",p.as_posix())
    if git("diff","--cached","--quiet",ok=(0,1))==0:
        print("ATOMIC_PIT_ALREADY_PERSISTED");return
    git("commit","-m","evidence(over25): immutable 5-source prospective PIT research snapshot")
    for _ in range(4):
        git("fetch","origin",BRANCH)
        git("rebase",f"origin/{BRANCH}")
        r=subprocess.run(["git","push","origin",f"HEAD:{BRANCH}"],
                         capture_output=True,text=True,check=False)
        if r.returncode==0:
            print("ATOMIC_PIT_EVIDENCE_PERSISTED")
            return
    raise RuntimeError("ATOMIC_PIT_EVIDENCE_PUSH_FAILED")

if __name__=="__main__":main()
