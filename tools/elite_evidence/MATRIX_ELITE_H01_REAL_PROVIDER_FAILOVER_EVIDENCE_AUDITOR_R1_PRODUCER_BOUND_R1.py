from __future__ import annotations
import argparse,json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA='MATRIX_ELITE_H01_REAL_PROVIDER_FAILOVER_EVIDENCE_R1'
INPUT_SCHEMA='MATRIX_ELITE_H01_REAL_PROVIDER_FAILOVER_INPUT_R1'
INPUT_CONTRACT_SHA256="86d04540166c7d3820d554c1f799dfcfe17c417d4ba374093b09c7ae6a9c4bd8"
PLAN_SCHEMA='MATRIX_ELITE_H01_PROVIDER_FAILOVER_DRILL_PLAN_R1'
APPROVAL_SCHEMA='MATRIX_ELITE_H01_FAILOVER_HUMAN_APPROVAL_EVIDENCE_R1'
CONTROL_SCHEMA='MATRIX_ELITE_H01_PROVIDER_CONTROL_EVIDENCE_R1'
DRILL_SCHEMA='MATRIX_ELITE_H01_PROVIDER_OUTAGE_DRILL_EVIDENCE_R1'
ANCHOR_SCHEMA='MATRIX_ELITE_TIMESTAMP_ANCHOR_VERIFICATION_R1'
ALLOWED_ANCHORS={'RFC3161_TSA','WORM_OBJECT_VERSION','EXTERNAL_AUDIT_LEDGER','SIGNED_TRANSPARENCY_LOG'}

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
def valid_sha(v:Any)->bool:
 try:return isinstance(v,str) and len(v)==64 and int(v,16)>=0
 except Exception:return False

def exact(pathv:Any,shav:Any,missing:str,mismatch:str):
 try:
  p=Path(pathv).resolve()
  if not p.is_file():return None,None,missing
  if fsha(p)!=shav:return p,None,mismatch
  return p,readj(p),None
 except Exception:return None,None,missing

def verify_anchor(anchor:dict[str,Any],expected_root:str,cutoff:datetime,errors:list[str]):
 try:
  if anchor.get('anchor_type') not in ALLOWED_ANCHORS or anchor.get('verification_result')!='PASS':raise ValueError('FAILOVER_ANCHOR_NOT_VERIFIED')
  if anchor.get('root_sha256')!=expected_root:raise ValueError('FAILOVER_ANCHOR_ROOT_MISMATCH')
  if dt(anchor['anchored_at'])>=cutoff:raise ValueError('FAILOVER_PLAN_NOT_ANCHORED_BEFORE_DRILL')
  p=Path(anchor['anchor_evidence_path']).resolve()
  if not p.is_file() or fsha(p)!=anchor.get('anchor_evidence_sha256'):raise ValueError('FAILOVER_ANCHOR_EVIDENCE_MISMATCH')
  j=readj(p)
  if j.get('schema')!=ANCHOR_SCHEMA or j.get('result')!='PASS' or j.get('root_sha256')!=expected_root or j.get('anchor_type')!=anchor.get('anchor_type') or dt(j['anchored_at'])!=dt(anchor['anchored_at']):raise ValueError('FAILOVER_ANCHOR_VERIFICATION_INVALID')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);ns=ap.parse_args();ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip);errors=[]
 if data.get('schema')!=INPUT_SCHEMA:errors.append('INPUT_SCHEMA_MISMATCH')
 pp,plan,e=exact(data.get('failover_plan_path'),data.get('failover_plan_sha256'),'FAILOVER_PLAN_MISSING','FAILOVER_PLAN_SHA_MISMATCH')
 if e:errors.append(e);plan={}
 elif plan.get('schema')!=PLAN_SCHEMA:errors.append('FAILOVER_PLAN_SCHEMA_MISMATCH')
 try:
  registered=dt(plan['registered_at']);start=dt(plan['drill_start_at']);end=dt(plan['drill_end_at'])
  if registered>=start:errors.append('FAILOVER_PLAN_NOT_REGISTERED_BEFORE_DRILL')
  if end<=start:errors.append('FAILOVER_DRILL_WINDOW_INVALID')
  if plan.get('environment') not in {'STAGING','SHADOW'}:errors.append('FAILOVER_DRILL_ENVIRONMENT_INVALID')
  if bool(plan.get('automatic_provider_switch_allowed')):errors.append('AUTOMATIC_PROVIDER_SWITCH_MUST_BE_FORBIDDEN')
  if float(plan['minimum_secondary_coverage'])<=0 or float(plan['minimum_secondary_coverage'])>1:errors.append('FAILOVER_COVERAGE_POLICY_INVALID')
  if not 0<float(plan['minimum_overlap_rate'])<=1 or not 0<=float(plan['maximum_disagreement_rate'])<1:errors.append('FAILOVER_RECONCILIATION_POLICY_INVALID')
  verify_anchor(data.get('plan_registration_anchor') or {},fsha(pp),start,errors)
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc));start=end=None

 # Control evidence: rights, schema, freshness for secondary.
 controls={}
 for typ,key in [('RIGHTS','secondary_rights_evidence'),('SCHEMA','secondary_schema_evidence'),('FRESHNESS','secondary_freshness_evidence')]:
  p,j,e=exact(data.get(key+'_path'),data.get(key+'_sha256'),typ+'_EVIDENCE_MISSING',typ+'_EVIDENCE_SHA_MISMATCH')
  if e:errors.append(e);continue
  if j.get('schema')!=CONTROL_SCHEMA or j.get('result')!='PASS' or j.get('control_type')!=typ:errors.append(typ+'_EVIDENCE_NOT_PASS');continue
  if str(j.get('provider'))!=str(plan.get('secondary_provider')):errors.append(typ+'_EVIDENCE_PROVIDER_MISMATCH')
  controls[typ]=j

 dp,drill,e=exact(data.get('outage_drill_evidence_path'),data.get('outage_drill_evidence_sha256'),'OUTAGE_DRILL_EVIDENCE_MISSING','OUTAGE_DRILL_EVIDENCE_SHA_MISMATCH')
 if e:errors.append(e);drill={}
 elif drill.get('schema')!=DRILL_SCHEMA or drill.get('result')!='PASS':errors.append('OUTAGE_DRILL_NOT_PASS')
 try:
  detected=dt(drill['primary_failure_detected_at']);switch=dt(drill['switch_executed_at']);rollback=dt(drill['rollback_completed_at'])
  if start and not(start<=detected<switch<rollback<=end):errors.append('FAILOVER_DRILL_TIMELINE_INVALID')
  if drill.get('environment')!=plan.get('environment'):errors.append('FAILOVER_DRILL_ENVIRONMENT_MISMATCH')
  if drill.get('primary_provider')!=plan.get('primary_provider') or drill.get('secondary_provider')!=plan.get('secondary_provider'):errors.append('FAILOVER_PROVIDER_SCOPE_MISMATCH')
  if not bool(drill.get('primary_outage_injected')) or not bool(drill.get('primary_unhealthy_observed')):errors.append('PRIMARY_OUTAGE_NOT_PROVEN')
  if bool(drill.get('automatic_switch_performed')):errors.append('AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN')
  if int(drill.get('orders_submitted',-1))!=0 or int(drill.get('wagers_executed',-1))!=0:errors.append('FAILOVER_DRILL_WAGERING_ACTIVITY_FORBIDDEN')
  if not bool(drill.get('rollback_completed')):errors.append('FAILOVER_ROLLBACK_REQUIRED')
  if float(drill.get('data_loss_fraction',1))>float(plan['maximum_data_loss_fraction']):errors.append('FAILOVER_DATA_LOSS_BREACH')
  if float(drill.get('recovery_seconds',1e18))>float(plan['maximum_recovery_seconds']):errors.append('FAILOVER_RECOVERY_TIME_BREACH')
  if not valid_sha(drill.get('audit_log_sha256')):errors.append('FAILOVER_AUDIT_LOG_SHA_REQUIRED')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc));detected=switch=rollback=None

 # Human approval must be real evidence after failure detection and before switch.
 apath,approval,e=exact(data.get('human_approval_evidence_path'),data.get('human_approval_evidence_sha256'),'FAILOVER_APPROVAL_EVIDENCE_MISSING','FAILOVER_APPROVAL_EVIDENCE_SHA_MISMATCH')
 if e:errors.append(e);approval={}
 elif approval.get('schema')!=APPROVAL_SCHEMA or approval.get('result')!='PASS':errors.append('FAILOVER_APPROVAL_NOT_PASS')
 try:
  approved=dt(approval['approved_at'])
  if detected and not(detected<=approved<switch):errors.append('FAILOVER_APPROVAL_NOT_BETWEEN_FAILURE_AND_SWITCH')
  if approval.get('primary_provider')!=plan.get('primary_provider') or approval.get('secondary_provider')!=plan.get('secondary_provider'):errors.append('FAILOVER_APPROVAL_PROVIDER_MISMATCH')
  if approval.get('scope')!='ONE_SHADOW_OR_STAGING_FAILOVER_DRILL':errors.append('FAILOVER_APPROVAL_SCOPE_INVALID')
  if not str(approval.get('approver','')).strip() or not valid_sha(approval.get('approval_record_sha256')):errors.append('FAILOVER_APPROVAL_IDENTITY_OR_HASH_REQUIRED')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

 # Provider snapshot reconciliation is computed by the auditor.
 primary=dict(data.get('primary_snapshot') or {});secondary=dict(data.get('secondary_snapshot') or {})
 pkeys=set(primary);skeys=set(secondary);overlap=pkeys&skeys;union=pkeys|skeys;dis=sum(primary[k]!=secondary[k] for k in overlap)
 overlap_rate=len(overlap)/len(union) if union else 0.0;dis_rate=dis/len(overlap) if overlap else 1.0;secondary_coverage=float(data.get('secondary_coverage',0))
 if secondary_coverage<float(plan.get('minimum_secondary_coverage',1)):errors.append('SECONDARY_COVERAGE_INSUFFICIENT')
 if overlap_rate<float(plan.get('minimum_overlap_rate',1)):errors.append('PROVIDER_OVERLAP_INSUFFICIENT')
 if dis_rate>float(plan.get('maximum_disagreement_rate',0)):errors.append('PROVIDER_DISAGREEMENT_TOO_HIGH')

 # Post-switch verification proves no silent semantic divergence and rollback safety.
 post=dict(data.get('post_switch_verification') or {})
 try:
  if post.get('result')!='PASS':errors.append('POST_SWITCH_VERIFICATION_NOT_PASS')
  if float(post['disagreement_rate'])>float(plan['maximum_post_switch_disagreement_rate']):errors.append('POST_SWITCH_DISAGREEMENT_BREACH')
  if int(post['missing_records'])!=0:errors.append('POST_SWITCH_MISSING_RECORDS')
  if not valid_sha(post['comparison_manifest_sha256']):errors.append('POST_SWITCH_COMPARISON_MANIFEST_SHA_REQUIRED')
  if not bool(post['rollback_primary_health_reverified']):errors.append('ROLLBACK_PRIMARY_HEALTH_REVERIFICATION_REQUIRED')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

 # Secondary controls must all be PASS and observed before switch.
 for typ,j in controls.items():
  try:
   if dt(j['observed_at'])>=switch:errors.append(typ+'_EVIDENCE_NOT_AVAILABLE_BEFORE_SWITCH')
  except Exception:errors.append(typ+'_EVIDENCE_TIME_INVALID')

 passed=not errors
 out={'schema':SCHEMA,'result':'PASS' if passed else 'FAIL_CLOSED','running_auditor_path':str(Path(__file__).resolve()),'running_auditor_sha256':sha256(Path(__file__).resolve().read_bytes()).hexdigest(),'input_contract_sha256':INPUT_CONTRACT_SHA256,'input_path':str(ip),'input_sha256':fsha(ip),
      'metrics':{'secondary_coverage':secondary_coverage,'overlap_rate':overlap_rate,'disagreement_rate_on_overlap':dis_rate,'overlap_keys':len(overlap),'disagreement_count':dis},
      'blocking_codes':sorted(set(errors)),'h01_real_provider_failover_evidence_passed':passed,'automatic_provider_switch_authorized':False,'orders_submitted':0,'wagers_executed':0,'controlled_live_admissible':False,'production_admissible':False,'output_payload_sha256':None}
 h=dict(out);h['output_payload_sha256']=None;out['output_payload_sha256']=canon(h)
 op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 print('RESULT='+('PASS' if passed else 'FAIL_CLOSED'));print('H01_REAL_PROVIDER_FAILOVER_EVIDENCE='+('PASS' if passed else 'FAIL'));print('AUTOMATIC_PROVIDER_SWITCH_AUTHORIZED=FALSE');print('BLOCKING_CODES='+(','.join(sorted(set(errors))) if errors else '<NONE>'));print('CONTROLLED_LIVE_ADMISSIBLE=FALSE');print('PRODUCTION_ADMISSIBLE=FALSE');print('EVIDENCE='+str(op));print('EVIDENCE_SHA256='+fsha(op));return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
