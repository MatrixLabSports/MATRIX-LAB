"""Persist one immutable, exact-source research PIT cycle.

This prevents a daily intake updated by a later workflow from pairing with
an older attestation. Only authenticated source objects, NEVER secrets,
production p_matrix, Telegram messages or execution instructions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA="MATRIX_CHAMPIONSHIP_ATOMIC_PIT_CYCLE_V1"
REQUIRED={
    "intake":"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
    "shadow":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json",
    "sofa":"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
    "flash":"MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",
    "attestation":"MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION.json",
}
BINDINGS={
    "intake":"source_intake_sha256",
    "shadow":"source_shadow_sha256",
    "sofa":"source_sofa_sha256",
    "flash":"source_flash_sha256",
}

def digest(doc):
    return hashlib.sha256(json.dumps(doc,sort_keys=True,ensure_ascii=False,
        separators=(",",":")).encode("utf-8")).hexdigest()

def utc(x):
    dt=datetime.fromisoformat(str(x).replace("Z","+00:00"))
    if dt.utcoffset() is None:
        raise ValueError("ATOMIC_PIT_TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)

def pack(docs,*,run_id):
    if not str(run_id).isdigit() or not all(k in docs for k in REQUIRED):
        raise ValueError("ATOMIC_PIT_UNTRUSTED_RUN_OR_MISSING_DOCUMENTS")
    a=docs["attestation"]
    d=docs["intake"].get("target_date_bogota")
    if (a.get("source_binding_schema")!="MATRIX_PROSPECTIVE_PIT_EXACT_FOUR_SOURCE_BINDING_V1"
        or a.get("schema")!="MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION_V1"
        or a.get("production_p_matrix_authorized_count")!=0
        or a.get("telegram_signal_authorized") is not False):
        raise ValueError("ATOMIC_PIT_UNVERIFIED_ATTESTATION")
    for key in REQUIRED:
        if docs[key].get("target_date_bogota")!=d or docs[key].get("real_money")!="BLOCKED":
            raise ValueError("ATOMIC_PIT_SOURCE_SCOPE_OR_FINANCIAL_SAFETY")
    for key,bind in BINDINGS.items():
        if a.get(bind)!=digest(docs[key]):
            raise ValueError("ATOMIC_PIT_SOURCE_HASH_MISMATCH_"+key.upper())
    at=utc(a["observed_at_utc"])
    start=utc(docs["intake"]["generated_at_utc"])
    end=utc(docs["shadow"]["completed_at_utc"])
    if (not start<=end<=at or (at-start).total_seconds()>1800):
        raise ValueError("ATOMIC_PIT_SOURCE_TIME_ORDER_INVALID")
    return {
        "schema":SCHEMA,"target_date_bogota":d,"run_id":str(run_id),
        "attested_at_utc":at.isoformat(),
        "source_sha256":{k:digest(v) for k,v in docs.items()},
        "documents":docs,
        "research_only":True,
        "prospective_research_history_certified_count":a.get(
            "prospective_research_history_certified_count",0),
        "production_probability_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED",
    }

def unpack(bundle):
    if (bundle.get("schema")!=SCHEMA
        or bundle.get("real_money")!="BLOCKED"
        or bundle.get("automatic_wagering") is not False
        or bundle.get("telegram_signal_authorized") is not False
        or bundle.get("production_probability_authorized") is not False
        or bundle.get("research_only") is not True):
        raise ValueError("ATOMIC_PIT_UNTRUSTED_BUNDLE")
    docs=bundle.get("documents")
    if not isinstance(docs,dict):
        raise ValueError("ATOMIC_PIT_BUNDLE_DOCUMENTS_MISSING")
    expected=pack(docs,run_id=bundle.get("run_id"))
    if expected!=bundle:
        raise ValueError("ATOMIC_PIT_BUNDLE_SNAPSHOT_MUTATED")
    return docs

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--run-id",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    expected_name=f"MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_{a.run_id}.json"
    if a.out.name!=expected_name or "daily_prematch_reports" in a.out.parts:
        raise SystemExit("ATOMIC_PIT_EVIDENCE_OUTPUT_INVALID")
    folder=a.root/"evidence"/"football_world_inventory"/a.date
    docs={k:json.loads((folder/v).read_text(encoding="utf-8"))
          for k,v in REQUIRED.items() if k!="attestation"}
    candidates=[
        folder/REQUIRED["attestation"],
        *sorted(folder.glob("MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_RUN_*.json")),
    ]
    valid=[]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            attestation=json.loads(candidate.read_text(encoding="utf-8"))
            b=pack({**docs,"attestation":attestation},run_id=a.run_id)
            valid.append((utc(attestation["observed_at_utc"]),candidate.name,b))
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
            continue
    if not valid:
        raise SystemExit("ATOMIC_PIT_NO_MATCHING_FIVE_DOCUMENT_SOURCE_CYCLE")
    _,chosen,b=max(valid,key=lambda x:(x[0],x[1]))
    if b["target_date_bogota"]!=a.date:
        raise SystemExit("ATOMIC_PIT_DATE_MISMATCH")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(b,sort_keys=True,ensure_ascii=False,indent=2)+"\n",
                     encoding="utf-8")
    print(json.dumps({"schema":b["schema"],"run_id":a.run_id,
                      "certified_history_count":b["prospective_research_history_certified_count"],
                      "source_attestation_file":chosen,
                      "telegram_signal_authorized":False,
                      "real_money":"BLOCKED"},sort_keys=True))

if __name__=="__main__":
    main()
