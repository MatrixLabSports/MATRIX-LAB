"""Inspect original API-Football canonical bundle manifests for frozen p_matrix.

Canonical ANALYSIS INPUTS (ready_input_count) must never be counted as frozen
probabilities. Read manifests only, SHA each source; no retroactive generation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from tools.matrix_six_league_existing_evidence_recovery import ROOT, relative_paths

OUTPUT=Path("evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_CANONICAL_PROBABILITY_MANIFEST_AUDIT_LAST.json")
MARKER="/canonical_analysis/manifest.json"
MAX_SIZE=3*1024*1024

def analyse(root:Path,tracked:list[str])->dict:
    found=sorted({p for p in tracked if p.startswith("evidence/api_football/prospective_daily/")
                  and p.endswith(MARKER)})
    values=Counter()
    exceptions=[]
    positive=[]
    total_ready=0
    for relative in found:
        file=root/relative
        try:
            if file.stat().st_size>MAX_SIZE:raise ValueError("MANIFEST_TOO_LARGE")
            data=json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(data,dict):raise ValueError("MANIFEST_NOT_OBJECT")
            if data.get("provider")!="api_football":
                raise ValueError("NOT_ORIGINAL_PROVIDER")
            if data.get("real_money")!="BLOCKED":
                raise ValueError("ORIGINAL_MANIFEST_MONEY_POLICY_INVALID")
            frozen=data.get("model_probability_generated")
            status=data.get("p_matrix_status")
            if not isinstance(frozen,bool) or not isinstance(status,str):
                raise ValueError("ORIGINAL_MANIFEST_PROBABILITY_STATUS_UNVERIFIED")
            ready=data.get("ready_input_count",0)
            if isinstance(ready,bool) or not isinstance(ready,int) or ready<0:
                raise ValueError("ORIGINAL_READY_INPUT_COUNT_INVALID")
            total_ready+=ready
            values["verified_manifests"]+=1
            values["generated_true" if frozen else "generated_false"]+=1
            values["p_matrix_status:"+status]+=1
            if frozen or status not in {"NOT_GENERATED","NO_GOVERNED_P_MATRIX"}:
                positive.append({"path":relative,"p_matrix_status":status,
                    "model_probability_generated":frozen,
                    "sha256":hashlib.sha256(file.read_bytes()).hexdigest(),
                    "ready_input_count":ready})
        except (OSError,TypeError,ValueError,KeyError,json.JSONDecodeError) as exc:
            exceptions.append({"path":relative,"reason":str(exc)[:100]})
    return {
        "schema":"MATRIX_ORIGINAL_CANONICAL_PROBABILITY_MANIFEST_AUDIT_V1",
        "status":"RESEARCH_MANIFEST_INVENTORY_NOT_P_MATRIX_CERTIFICATION",
        "canonical_manifest_file_count":len(found),
        "verified_manifest_count":values["verified_manifests"],
        "manifest_files_with_generated_probability_true":values["generated_true"],
        "manifest_files_with_generated_probability_false":values["generated_false"],
        "sum_ready_input_counts_across_snapshots_not_unique_fixtures":total_ready,
        "p_matrix_status_counts":{k[len("p_matrix_status:"):]:v for k,v in sorted(values.items())
                                  if k.startswith("p_matrix_status:")},
        "potential_probability_manifest_count":len(positive),
        "potential_probability_manifests":positive[:100],
        "rejected_manifest_count":len(exceptions),
        "rejected_manifest_examples":exceptions[:20],
        "does_not_scan_other_production_reports":True,
        "original_canonical_inputs_are_not_model_predictions":True,
        "six_league_prospective_parity_certified":False,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED"
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=OUTPUT)
    a=p.parse_args()
    if any(v in a.out.parts for v in ("telegram","governance","tennis_signals","daily_prematch_reports")):
        raise SystemExit("MATRIX_ORIGINAL_MANIFEST_AUDIT_MUST_NOT_WRITE_PRODUCTION")
    result=analyse(a.root,relative_paths(a.root))
    out=a.out if a.out.is_absolute() else a.root/a.out
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in (
        "canonical_manifest_file_count","verified_manifest_count",
        "manifest_files_with_generated_probability_true",
        "potential_probability_manifest_count","rejected_manifest_count",
        "telegram_signal_authorized")},sort_keys=True))

if __name__=="__main__":main()
