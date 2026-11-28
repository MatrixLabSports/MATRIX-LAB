"""Commit only an immutable fail-closed Over 2.5 recovery audit; no signals."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path

BRANCH="repair/cor09-world-pipeline"

def git(*args,ok=(0,)):
    r=subprocess.run(["git",*args],capture_output=True,text=True,check=False)
    if r.returncode not in ok:
        raise RuntimeError(f"TRUTH_EVIDENCE_GIT_{args[0]}_FAILED_{r.returncode}")
    return r.returncode

def main():
    run=os.environ.get("GITHUB_RUN_ID","")
    if not run.isdigit():raise ValueError("TRUTH_GUARD_RUN_ID_INVALID")
    file=Path("evidence/notifications/telegram")/f"MATRIX_OVER25_RECOVERY_TRUTH_{run}.json"
    r=json.loads(file.read_text(encoding="utf-8"))
    if (r.get("schema")!="MATRIX_OVER25_TELEGRAM_RECOVERY_TRUTH_GUARD_V1"
        or r.get("status")!="NO_GO_FAIL_CLOSED"
        or r.get("real_money")!="BLOCKED"
        or r.get("automatic_wagering") is not False
        or r.get("telegram_messages_sent")!=0
        or r.get("signal_generation_authorized") is not False
        or r.get("p_matrix_production_export_created") is not False
        or not r.get("blockers")):
        raise ValueError("TRUTH_GUARD_PERSIST_BLOCKED_UNSAFE")
    git("config","user.name","matrix-over25-truth-guard")
    git("config","user.email","matrix-over25-truth-guard@users.noreply.github.com")
    git("add","--",file.as_posix())
    if git("diff","--cached","--quiet",ok=(0,1))==0:
        print("TRUTH_GUARD_EVIDENCE_UNCHANGED")
        return
    git("commit","-m","evidence(over25): persist read-only physical readiness and exact blockers")
    for _ in range(4):
        git("fetch","origin",BRANCH)
        git("rebase",f"origin/{BRANCH}")
        r=subprocess.run(["git","push","origin",f"HEAD:{BRANCH}"],
                         capture_output=True,text=True,check=False)
        if r.returncode==0:
            print("TRUTH_GUARD_EVIDENCE_PERSISTED")
            return
    raise RuntimeError("TRUTH_GUARD_EVIDENCE_PUSH_FAILED")

if __name__=="__main__":
    main()
