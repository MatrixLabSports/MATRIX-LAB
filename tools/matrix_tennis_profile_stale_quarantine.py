"""Preserve genuine tennis browser intake when old biography PIT evidence is stale.

Never convert stale biography into certified Hard/Clay ratings. Only the exact
PROFILE_AUDIT_PRECUT_HISTORY_NOT_PRECUT exception is quarantinable; all other
errors stay fatal. Provides physical dated proof to downstream drift gate.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_tennis_free_profile_source_binding_audit import main as original_main

SCHEMA="MATRIX_TENNIS_FREE_BIOGRAPHY_STALE_SOURCE_QUARANTINE_V1"
def run(day,*,root=Path("."),runner=subprocess.run):
    day=str(day)
    paths=[
      Path("evidence/tennis_calendar_physical")/day/"MATRIX_TENNIS_FREE_VISIBLE_PROFILE_BIRTHDATES_RESEARCH.json",
      Path("evidence/tennis_calendar_physical")/day/"sofascore_verified_match_details.json"]
    if not all((root/p).is_file() for p in paths):
        return {"schema":SCHEMA,"target_date_bogota":day,"status":"MISSING_PROFILE_OR_DETAIL_SOURCE",
          "quarantined":False,"source_files_sha256":{},"model_admission_authorized":False,
          "hard_holdout_admitted":0,"clay_holdout_admitted":0,"real_money":"BLOCKED"}
    sha={str(p):hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    cp=runner([sys.executable,"-m","tools.matrix_tennis_free_profile_source_binding_audit",
        "--date",day],capture_output=True,text=True,timeout=90)
    stdout=str(cp.stdout or "");stderr=str(cp.stderr or "")
    if cp.returncode==0:
        status="CURRENT_PROFILE_PIT_BINDING_COMPLETED"
        quarantine=False
    elif "PROFILE_AUDIT_PRECUT_HISTORY_NOT_PRECUT" in stderr:
        status="STALE_PROFILE_PRE_CUT_EVIDENCE_QUARANTINED_NO_MODEL_ADMISSION"
        quarantine=True
    else:
        raise RuntimeError("UNEXPECTED_TENNIS_PROFILE_AUDIT_FAILURE:"+str(cp.returncode)+":"+stderr[-800:])
    return {"schema":SCHEMA,"target_date_bogota":day,
      "observed_at_utc":datetime.now(timezone.utc).isoformat(),
      "status":status,"quarantined":quarantine,"source_files_sha256":sha,
      "profile_binding_command_exit_code":int(cp.returncode),
      "old_profile_pre_cut_is_not_new_prospective_match":True,
      "model_admission_authorized":False,"hard_holdout_admitted":0,"clay_holdout_admitted":0,
      "telegram_signal_authorized":False,"automatic_wagering":False,"real_money":"BLOCKED"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--date",required=True)
    args=p.parse_args()
    j=run(args.date)
    out=Path("evidence/tennis_calendar_reconciliation")/args.date/"MATRIX_TENNIS_PROFILE_PIT_SOURCE_QUARANTINE_LAST.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":j["status"],"quarantined":j["quarantined"],"source_files":len(j["source_files_sha256"]),"holdout_admitted":0}))
if __name__=="__main__":main()
