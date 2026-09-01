from __future__ import annotations
import argparse,json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA='MATRIX_ELITE_H05_REAL_CI_CD_SUPPLY_CHAIN_EVIDENCE_R1'
INPUT_SCHEMA='MATRIX_ELITE_H05_REAL_CI_CD_SUPPLY_CHAIN_INPUT_R1'
INPUT_CONTRACT_SHA256="289af7b1aa702c9da90eb5cb4c5781e430c4d142f932c7acb82304b6b3fef024"
POLICY_SCHEMA='MATRIX_ELITE_H05_CI_POLICY_R1'
RUN_SCHEMA='MATRIX_ELITE_H05_CI_RUN_EVIDENCE_R1'
GATE_SCHEMA='MATRIX_ELITE_H05_CI_GATE_EVIDENCE_R1'
VERIFY_SCHEMA='MATRIX_ELITE_H05_VERIFICATION_EVIDENCE_R1'
PROTECTION_SCHEMA='MATRIX_ELITE_H05_BRANCH_PROTECTION_EVIDENCE_R1'
PROVENANCE_SCHEMA='MATRIX_ELITE_H05_BUILD_PROVENANCE_EVIDENCE_R1'
REQUIRED_GATES=('lint','unit','integration','data','security','secret_scan','dependency_scan','coverage','schema','sport_boundary','model_validation','build','sbom','artifact_signing')

def dt(v:str)->datetime:
 x=datetime.fromisoformat(str(v).replace('Z','+00:00'))
 if x.tzinfo is None or x.utcoffset() is None:raise ValueError('TIME_MUST_BE_TIMEZONE_AWARE')
 return x

def readj(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding='utf-8-sig'))
 if not isinstance(x,dict):raise ValueError('JSON_ROOT_MUST_BE_OBJECT')
 return x

def fsha(p:Path)->str:return sha256(p.read_bytes()).hexdigest()
def canon(x:Any)->str:return sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def valid_sha(v:Any,n=64)->bool:
 try:return isinstance(v,str) and len(v)==n and int(v,16)>=0
 except Exception:return False

def exact(pathv,shav,missing,mismatch):
 try:
  p=Path(pathv).resolve()
  if not p.is_file():return None,None,missing
  if fsha(p)!=shav:return p,None,mismatch
  return p,readj(p),None
 except Exception:return None,None,missing

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);ns=ap.parse_args();ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip);errors=[]
 if data.get('schema')!=INPUT_SCHEMA:errors.append('INPUT_SCHEMA_MISMATCH')
 pp,policy,e=exact(data.get('ci_policy_path'),data.get('ci_policy_sha256'),'CI_POLICY_MISSING','CI_POLICY_SHA_MISMATCH')
 if e:errors.append(e);policy={}
 elif policy.get('schema')!=POLICY_SCHEMA:errors.append('CI_POLICY_SCHEMA_MISMATCH')
 try:
  expected=str(policy['expected_commit_sha'])
  if not valid_sha(expected,40):errors.append('CI_EXPECTED_COMMIT_INVALID')
  if policy.get('branch')!='main':errors.append('CI_POLICY_BRANCH_MUST_BE_MAIN')
  if set(policy['required_gates'])!=set(REQUIRED_GATES):errors.append('CI_REQUIRED_GATE_SET_MISMATCH')
  if float(policy['minimum_coverage_fraction'])<=0 or float(policy['minimum_coverage_fraction'])>1:errors.append('CI_COVERAGE_POLICY_INVALID')
  if bool(policy.get('automatic_model_promotion')) or bool(policy.get('automatic_provider_switch')) or bool(policy.get('automatic_wagering')):errors.append('CI_AUTOMATION_SAFETY_POLICY_INVALID')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc));expected=''

 rp,run,e=exact(data.get('ci_run_evidence_path'),data.get('ci_run_evidence_sha256'),'CI_RUN_EVIDENCE_MISSING','CI_RUN_EVIDENCE_SHA_MISMATCH')
 if e:errors.append(e);run={}
 elif run.get('schema')!=RUN_SCHEMA or run.get('result')!='PASS':errors.append('CI_RUN_NOT_PASS')
 try:
  if run['commit_sha']!=expected:errors.append('CI_COMMIT_MISMATCH')
  if run['branch']!='main':errors.append('CI_RUN_BRANCH_MISMATCH')
  dt(run['completed_at'])
  if not str(run['provider']).strip() or not str(run['run_id']).strip():errors.append('CI_PROVIDER_RUN_ID_REQUIRED')
  if bool(run.get('automatic_model_promotion')) or bool(run.get('automatic_provider_switch')) or bool(run.get('automatic_wagering')):errors.append('CI_RUN_AUTOMATION_SAFETY_VIOLATION')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

 # Every CI gate carries exact evidence bound to the same commit.
 gates=data.get('gate_evidence') or {};gate_metrics={}
 for gate in REQUIRED_GATES:
  ref=gates.get(gate)
  if not isinstance(ref,dict):errors.append('CI_GATE_EVIDENCE_MISSING:'+gate);continue
  gp,g,e=exact(ref.get('path'),ref.get('sha256'),'CI_GATE_FILE_MISSING:'+gate,'CI_GATE_SHA_MISMATCH:'+gate)
  if e:errors.append(e);continue
  if g.get('schema')!=GATE_SCHEMA or g.get('result')!='PASS' or g.get('gate')!=gate:errors.append('CI_GATE_NOT_PASS:'+gate);continue
  if g.get('commit_sha')!=expected:errors.append('CI_GATE_COMMIT_MISMATCH:'+gate)
  if gate=='coverage':
   cov=float(g.get('coverage_fraction',-1));gate_metrics['coverage_fraction']=cov
   if cov<float(policy['minimum_coverage_fraction']):errors.append('CI_COVERAGE_BELOW_THRESHOLD')
  if gate in {'security','secret_scan','dependency_scan'}:
   if int(g.get('critical_findings',-1))!=0:errors.append('CI_CRITICAL_FINDINGS_PRESENT:'+gate)
   if int(g.get('high_findings',-1))>int(policy['maximum_high_findings']):errors.append('CI_HIGH_FINDINGS_EXCEED_POLICY:'+gate)

 # Exact lock/SBOM/artifact files.
 for label,pathkey,shakey in [('DEPENDENCY_LOCK','dependency_lock_path','dependency_lock_sha256'),('SBOM','sbom_path','sbom_sha256'),('BUILD_ARTIFACT','build_artifact_path','build_artifact_sha256')]:
  try:
   p=Path(data[pathkey]).resolve()
   if not p.is_file():errors.append(label+'_FILE_MISSING')
   elif fsha(p)!=data.get(shakey):errors.append(label+'_HASH_MISMATCH')
  except Exception:errors.append(label+'_FILE_MISSING')

 # Verification evidence binds exact objects.
 for typ,pathkey,shakey,targetkey in [('DEPENDENCY_LOCK','dependency_lock_verification_path','dependency_lock_verification_sha256','dependency_lock_sha256'),('SBOM','sbom_verification_path','sbom_verification_sha256','sbom_sha256'),('ARTIFACT_SIGNATURE','artifact_signature_verification_path','artifact_signature_verification_sha256','build_artifact_sha256')]:
  p,j,e=exact(data.get(pathkey),data.get(shakey),typ+'_VERIFICATION_MISSING',typ+'_VERIFICATION_SHA_MISMATCH')
  if e:errors.append(e);continue
  if j.get('schema')!=VERIFY_SCHEMA or j.get('result')!='PASS' or j.get('verification_type')!=typ:errors.append(typ+'_VERIFICATION_NOT_PASS')
  if j.get('target_sha256')!=data.get(targetkey):errors.append(typ+'_VERIFICATION_TARGET_MISMATCH')
  if not str(j.get('verifier','')).strip():errors.append(typ+'_VERIFIER_REQUIRED')

 # Build provenance exact commit/artifact and reproducibility evidence.
 p,prov,e=exact(data.get('build_provenance_evidence_path'),data.get('build_provenance_evidence_sha256'),'BUILD_PROVENANCE_MISSING','BUILD_PROVENANCE_SHA_MISMATCH')
 if e:errors.append(e);prov={}
 elif prov.get('schema')!=PROVENANCE_SCHEMA or prov.get('result')!='PASS':errors.append('BUILD_PROVENANCE_NOT_PASS')
 try:
  if prov['source_commit_sha']!=expected or prov['build_artifact_sha256']!=data.get('build_artifact_sha256'):errors.append('BUILD_PROVENANCE_BINDING_MISMATCH')
  if prov['dependency_lock_sha256']!=data.get('dependency_lock_sha256') or prov['sbom_sha256']!=data.get('sbom_sha256'):errors.append('BUILD_PROVENANCE_INPUT_BINDING_MISMATCH')
  if bool(policy.get('reproducible_build_required')) and prov.get('independent_rebuild_artifact_sha256')!=data.get('build_artifact_sha256'):errors.append('REPRODUCIBLE_BUILD_HASH_MISMATCH')
 except (KeyError,TypeError) as exc:errors.append(str(exc))

 # Branch protection is read evidence, not a claim in CI run.
 p,bp,e=exact(data.get('branch_protection_evidence_path'),data.get('branch_protection_evidence_sha256'),'BRANCH_PROTECTION_EVIDENCE_MISSING','BRANCH_PROTECTION_EVIDENCE_SHA_MISMATCH')
 if e:errors.append(e);bp={}
 elif bp.get('schema')!=PROTECTION_SCHEMA or bp.get('result')!='PASS':errors.append('BRANCH_PROTECTION_NOT_PASS')
 try:
  if bp['branch']!='main':errors.append('BRANCH_PROTECTION_SCOPE_MISMATCH')
  for k in ('required_reviews','status_checks_required','force_push_disabled','deletion_disabled'):
   if not bool(bp[k]):errors.append('BRANCH_PROTECTION_CONTROL_MISSING:'+k)
 except (KeyError,TypeError) as exc:errors.append(str(exc))

 # The gate may audit a release candidate but never grants production itself.
 production_requested=bool(data.get('production_release_requested',False))
 if production_requested:
  p,a,e=exact(data.get('human_release_approval_path'),data.get('human_release_approval_sha256'),'HUMAN_RELEASE_APPROVAL_MISSING','HUMAN_RELEASE_APPROVAL_SHA_MISMATCH')
  if e:errors.append(e)
  else:
   if a.get('result')!='PASS' or a.get('commit_sha')!=expected or not str(a.get('approver','')).strip():errors.append('HUMAN_RELEASE_APPROVAL_INVALID')

 passed=not errors
 out={'schema':SCHEMA,'result':'PASS' if passed else 'FAIL_CLOSED','running_auditor_path':str(Path(__file__).resolve()),'running_auditor_sha256':sha256(Path(__file__).resolve().read_bytes()).hexdigest(),'input_contract_sha256':INPUT_CONTRACT_SHA256,'input_path':str(ip),'input_sha256':fsha(ip),'commit_sha':expected,'metrics':gate_metrics,'blocking_codes':sorted(set(errors)),'h05_real_ci_cd_supply_chain_evidence_passed':passed,'production_release_requested':production_requested,'automatic_model_promotion':False,'automatic_provider_switch':False,'automatic_wagering':False,'controlled_live_admissible':False,'production_admissible':False,'output_payload_sha256':None}
 h=dict(out);h['output_payload_sha256']=None;out['output_payload_sha256']=canon(h);op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 print('RESULT='+('PASS' if passed else 'FAIL_CLOSED'));print('H05_REAL_CI_CD_SUPPLY_CHAIN_EVIDENCE='+('PASS' if passed else 'FAIL'));print('BLOCKING_CODES='+(','.join(sorted(set(errors))) if errors else '<NONE>'));print('PRODUCTION_ADMISSIBLE=FALSE');print('EVIDENCE='+str(op));print('EVIDENCE_SHA256='+fsha(op));return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
