"""Persist only a safety-verified research-only Championship PIT attestation."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

PATH=Path("evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION.json")
BRANCH="repair/cor09-world-pipeline"

def run(*args, allowed=(0,)):
    p=subprocess.run(["git",*args],capture_output=True,text=True,check=False)
    if p.returncode not in allowed:
        raise RuntimeError(f"RESEARCH_EVIDENCE_GIT_FAILED:{args[0]}:{p.returncode}")
    return p.returncode

def main():
    report=json.loads(PATH.read_text(encoding="utf-8"))
    if (report.get("schema")!="MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION_V1"
        or report.get("real_money")!="BLOCKED"
        or report.get("automatic_wagering") is not False
        or report.get("telegram_signal_authorized") is not False
        or report.get("production_p_matrix_authorized_count")!=0
        or report.get("calibration_untouched") is not True
        or any(row.get("governed_probability_authorized") is not False for row in report.get("rows",[]))):
        raise ValueError("PROSPECTIVE_PIT_RESEARCH_GOVERNANCE_INVALID")
    run("config","user.name","matrix-prospective-pit-audit")
    run("config","user.email","matrix-prospective-pit-audit@users.noreply.github.com")
    run("add","--",PATH.as_posix())
    if run("diff","--cached","--quiet",allowed=(0,1))==0:
        print("PROSPECTIVE_PIT_REPORT_UNCHANGED")
        return
    run("commit","-m","evidence(over25): preserve authentic Championship pre-kickoff PIT research")
    for _ in range(4):
        run("fetch","origin",BRANCH)
        run("rebase",f"origin/{BRANCH}")
        ret=subprocess.run(["git","push","origin",f"HEAD:{BRANCH}"],capture_output=True,check=False)
        if ret.returncode==0:
            print("PROSPECTIVE_PIT_REPORT_PERSISTED")
            return
    raise RuntimeError("PROSPECTIVE_PIT_REPORT_PUSH_FAILED")

if __name__=="__main__":
    main()
