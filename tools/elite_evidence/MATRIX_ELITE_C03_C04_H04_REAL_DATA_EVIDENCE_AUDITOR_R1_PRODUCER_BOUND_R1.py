from __future__ import annotations
import argparse, json
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from matrix_elite.data_admission import admit_training_snapshot
from matrix_elite.identity import CanonicalIdentityRegistry, IdentityBinding
from matrix_elite.pit import PITRecord, audit_minimum_coverage, audit_revision_graph, snapshot_as_of, snapshot_manifest
from matrix_elite.rights import RightsProfile, RightsRegistry

SCHEMA="MATRIX_ELITE_C03_C04_H04_REAL_DATA_EVIDENCE_R1"
INPUT_CONTRACT_SHA256="9c9957edf267682ecc98d73e59fed8ce75738be5da87c380e491ff6f9e5580db"

def dt(value: str | None) -> datetime | None:
    if value is None or value == "": return None
    out=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if out.tzinfo is None or out.utcoffset() is None: raise ValueError("TIME_MUST_BE_TIMEZONE_AWARE")
    return out

def load(path: Path) -> dict[str,Any]:
    data=json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data,dict): raise ValueError("INPUT_ROOT_MUST_BE_OBJECT")
    return data

def canonical_sha(obj: Any) -> str:
    raw=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return sha256(raw).hexdigest()

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--output",required=True)
    ns=ap.parse_args()
    ip=Path(ns.input).resolve(); op=Path(ns.output).resolve()
    data=load(ip)
    scope=data.get("scope") or {}
    sport=str(scope.get("sport","")).strip(); competition=str(scope.get("competition","")).strip(); market=str(scope.get("market","")).strip(); as_of=dt(scope.get("as_of_utc"))
    if not sport or not competition or not market or as_of is None: raise ValueError("SCOPE_REQUIRED")
    min_conf=float(data.get("minimum_identity_confidence",0.95))
    if not 0 <= min_conf <= 1: raise ValueError("MINIMUM_IDENTITY_CONFIDENCE_INVALID")
    required_rights=tuple(data.get("required_rights") or ("research","retention","derivatives","model_training"))

    records=[]
    for row in data.get("pit_records",[]):
        records.append(PITRecord(record_key=str(row["record_key"]),provider=str(row["provider"]),sport=str(row["sport"]),competition=str(row["competition"]),market=str(row["market"]),observed_at=dt(row["observed_at"]),available_at=dt(row["available_at"]),event_start_at=dt(row["event_start_at"]),revision_id=str(row["revision_id"]),revision_number=int(row["revision_number"]),payload_sha256=str(row["payload_sha256"]),supersedes_revision_id=row.get("supersedes_revision_id")))
    if not records: raise ValueError("PIT_RECORDS_REQUIRED")
    mixed=sorted({r.sport for r in records if r.sport != sport})
    scope_mismatch=[r.record_key for r in records if r.sport != sport or r.competition != competition or r.market != market]

    identities=CanonicalIdentityRegistry()
    binding_future_count=0
    for row in data.get("identity_bindings",[]):
        available=dt(row.get("available_at"))
        if available is not None and available > as_of: binding_future_count += 1
        identities.bind(IdentityBinding(provider=str(row["provider"]),provider_entity_id=str(row["provider_entity_id"]),canonical_entity_id=str(row["canonical_entity_id"]),confidence=float(row["confidence"]),evidence_sha256=str(row["evidence_sha256"]),status=str(row.get("status","CONFIRMED")),entity_type=str(row.get("entity_type","UNKNOWN")),available_at=available))
    identity_keys=[(str(x["provider"]),str(x["provider_entity_id"])) for x in data.get("identity_keys",[])]
    if not identity_keys: raise ValueError("IDENTITY_KEYS_REQUIRED")

    rights=RightsRegistry()
    for row in data.get("rights_profiles",[]):
        p=RightsProfile(provider=str(row["provider"]),research=bool(row["research"]),retention=bool(row["retention"]),derivatives=bool(row["derivatives"]),model_training=bool(row["model_training"]),display=bool(row.get("display",False)),redistribution=bool(row.get("redistribution",False)),commercial_use=bool(row.get("commercial_use",False)),expires_at=dt(row.get("expires_at")) if row.get("expires_at") else None,evidence_sha256=str(row["evidence_sha256"]),effective_from=dt(row.get("effective_from")),terminated_at=dt(row.get("terminated_at")),termination_reason=row.get("termination_reason"))
        rights.register(p,supersedes_evidence_sha256=row.get("supersedes_evidence_sha256"))

    graph=audit_revision_graph(records)
    snap=()
    snap_error=None
    try: snap=snapshot_as_of(records,as_of=as_of)
    except ValueError as exc: snap_error=str(exc)
    manifest=None
    if not graph and snap_error is None: manifest=snapshot_manifest(records,as_of=as_of)

    coverage_req={}
    for x in data.get("coverage_requirements",[]): coverage_req[(str(x["sport"]),str(x["competition"]),str(x["market"]),int(x["year"]))]=int(x["minimum"])
    coverage=audit_minimum_coverage(records,requirements=coverage_req) if coverage_req else {}
    coverage_rows=[{'sport':k[0],'competition':k[1],'market':k[2],'year':k[3],**v} for k,v in sorted(coverage.items())]
    coverage_pass=all(bool(x['pass']) for x in coverage_rows)
    identity_audit=list(identities.audit())
    crosswalk=identities.crosswalk_coverage(identity_keys)
    rights_audit=rights.audit_use(providers={r.provider for r in snap},purposes=required_rights,at=as_of) if snap else {'pass':False,'failures':[{'code':'NO_VALID_SNAPSHOT'}]}
    admission=admit_training_snapshot(records,as_of=as_of,identity_registry=identities,identity_keys=identity_keys,rights_registry=rights,required_rights=required_rights,minimum_identity_confidence=min_conf)
    extra_codes=[]
    if scope_mismatch: extra_codes.append("SCOPE_MISMATCH")
    if mixed: extra_codes.append("MIXED_SPORT_TRAINING_SNAPSHOT")
    if binding_future_count: extra_codes.append("FUTURE_IDENTITY_BINDINGS_PRESENT")
    if not coverage_pass: extra_codes.append("MINIMUM_COVERAGE_FAILED")
    if identity_audit: extra_codes.append("IDENTITY_REGISTRY_AUDIT_FAILED")
    admitted=bool(admission.admitted and not extra_codes)

    output={
      'schema':SCHEMA,'result':'PASS' if admitted else 'FAIL_CLOSED','running_auditor_path':str(Path(__file__).resolve()),'running_auditor_sha256':sha256(Path(__file__).resolve().read_bytes()).hexdigest(),'input_contract_sha256':INPUT_CONTRACT_SHA256,
      'input_path':str(ip),'input_sha256':sha256(ip.read_bytes()).hexdigest(),'scope':{'sport':sport,'competition':competition,'market':market,'as_of_utc':as_of.isoformat()},
      'record_count_input':len(records),'snapshot_record_count':len(snap),'snapshot_sha256':manifest.snapshot_sha256 if manifest else None,
      'revision_graph_violation_count':len(graph),'revision_graph_violations':[asdict(x) for x in graph],'snapshot_error':snap_error,
      'identity_key_count':len(identity_keys),'identity_manifest_sha256':identities.manifest_sha256(),'identity_audit_findings':identity_audit,'identity_crosswalk_coverage':crosswalk,'future_identity_binding_count':binding_future_count,
      'rights_audit':rights_audit,'required_rights':list(required_rights),'minimum_identity_confidence':min_conf,
      'coverage':coverage_rows,'coverage_pass':coverage_pass,'scope_mismatch_count':len(scope_mismatch),'scope_mismatch_keys':scope_mismatch[:100],
      'admission':{'admitted':admission.admitted,'codes':list(admission.codes),'snapshot_sha256':admission.snapshot_sha256,'record_count':admission.record_count},
      'extra_blocking_codes':sorted(set(extra_codes)),'admitted':admitted,'network_calls_performed':False,'controlled_live_admissible':False,'production_admissible':False,
      'output_payload_sha256':None,
    }
    hashable=dict(output);hashable['output_payload_sha256']=None;output['output_payload_sha256']=canonical_sha(hashable)
    op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("RESULT="+("PASS" if admitted else "FAIL_CLOSED"));print("C03_C04_H04_REAL_DATA_EVIDENCE="+("PASS" if admitted else "FAIL"));print("ADMITTED="+str(admitted).upper());print("SNAPSHOT_RECORD_COUNT="+str(len(snap)));print("REVISION_GRAPH_VIOLATIONS="+str(len(graph)));print("IDENTITY_COVERAGE="+str(crosswalk.get('resolved_rate')));print("RIGHTS_PASS="+str(bool(rights_audit.get('pass'))).upper());print("COVERAGE_PASS="+str(coverage_pass).upper());print("EVIDENCE="+str(op));print("EVIDENCE_SHA256="+sha256(op.read_bytes()).hexdigest())
    return 0 if admitted else 2

if __name__ == "__main__": raise SystemExit(main())
