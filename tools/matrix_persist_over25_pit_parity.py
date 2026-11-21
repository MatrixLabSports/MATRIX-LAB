"""Persist only the offline historical PIT report using installed Python.

No shell scripts, no OS policy changes, no model, stake or signal writes.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

PATH=Path("evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ENRICHED_RAW_PIT_REPLAY.json")
BRANCH="repair/cor09-world-pipeline"

def call(*args, allow_difference=False):
    result=subprocess.run(["git",*args],capture_output=True,text=True,check=False)
    if result.returncode and not (allow_difference and result.returncode==1):
        raise RuntimeError(f"GIT_OPERATION_FAILED:{args[0]}:returncode={result.returncode}")
    return result.returncode

def validate(j):
    if (j.get("schema")!="MATRIX_OVER25_ENRICHED_VS_RAW_GROUP_PIT_REPLAY_V1"
        or j.get("real_money")!="BLOCKED"
        or j.get("automatic_wagering") is not False
        or j.get("future_model_probability_authorized") is not False
        or j.get("canonical_inputs_generated") is not False
        or j.get("telegram_signal_authorized") is not False):
        raise ValueError("PIT_PERSIST_UNSAFE_EVIDENCE")
    if j.get("canonical_targets") != j.get("paired_targets",0)+j.get("blocked_targets",0):
        raise ValueError("PIT_PERSIST_COUNTS_INVALID")

def main():
    validate(json.loads(PATH.read_text(encoding="utf-8")))
    call("config","user.name","matrix-pit-parity-audit")
    call("config","user.email","matrix-pit-parity-audit@users.noreply.github.com")
    call("add","--",PATH.as_posix())
    if call("diff","--cached","--quiet",allow_difference=True)==0:
        print("PIT_PARITY_EVIDENCE_UNCHANGED")
        return
    call("commit","-m","evidence(over25): preserve archived enriched-vs-raw PIT comparison")
    for attempt in range(3):
        call("fetch","origin",BRANCH)
        call("rebase",f"origin/{BRANCH}")
        if subprocess.run(["git","push","origin",f"HEAD:{BRANCH}"],capture_output=True,check=False).returncode==0:
            print("PIT_PARITY_EVIDENCE_PERSISTED")
            return
    raise RuntimeError("PIT_PARITY_EVIDENCE_PUSH_FAILED")

if __name__=="__main__":
    main()
