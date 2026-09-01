from __future__ import annotations
import argparse,json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA='MATRIX_ELITE_H03_REAL_SRE_CONTINUITY_EVIDENCE_R1'
INPUT_SCHEMA='MATRIX_ELITE_H03_REAL_SRE_CONTINUITY_INPUT_R1'
INPUT_CONTRACT_SHA256="486048fbfb4f43284cd699f7db8dd0273355e5a17fde190737a40f94498b7664"
POLICY_SCHEMA='MATRIX_ELITE_H03_SRE_CONTINUITY_POLICY_R1'
BACKUP_SCHEMA='MATRIX_ELITE_H03_BACKUP_MANIFEST_R1'
RESTORE_SCHEMA='MATRIX_ELITE_H03_RESTORE_DRILL_EVIDENCE_R1'
LOAD_SCHEMA='MATRIX_ELITE_H03_LOAD_TEST_EVIDENCE_R1'
CHAOS_SCHEMA='MATRIX_ELITE_H03_CHAOS_TEST_EVIDENCE_R1'
ALERT_SCHEMA='MATRIX_ELITE_H03_ALERT_DELIVERY_EVIDENCE_R1'
TELEMETRY_SCHEMA='MATRIX_ELITE_H03_TELEMETRY_VALIDATION_EVIDENCE_R1'
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

def exact(pathv,shav,missing,mismatch):
 try:
  p=Path(pathv).resolve()
  if not p.is_file():return None,None,missing
  if fsha(p)!=shav:return p,None,mismatch
  return p,readj(p),None
 except Exception:return None,None,missing

def verify_plan_anchor(plan_path:Path,anchor:dict[str,Any],cutoff:datetime,errors:list[str]):
 try:
  if anchor.get('anchor_type') not in ALLOWED_ANCHORS or anchor.get('verification_result')!='PASS':raise ValueError('SRE_PLAN_ANCHOR_NOT_VERIFIED')
  if anchor.get('root_sha256')!=fsha(plan_path):raise ValueError('SRE_PLAN_ANCHOR_ROOT_MISMATCH')
  if dt(anchor['anchored_at'])>=cutoff:raise ValueError('SRE_PLAN_NOT_ANCHORED_BEFORE_DRILL')
  ep=Path(anchor['anchor_evidence_path']).resolve()
  if not ep.is_file() or fsha(ep)!=anchor.get('anchor_evidence_sha256'):raise ValueError('SRE_PLAN_ANCHOR_EVIDENCE_MISMATCH')
  j=readj(ep)
  if j.get('schema')!=ANCHOR_SCHEMA or j.get('result')!='PASS' or j.get('root_sha256')!=fsha(plan_path) or j.get('anchor_type')!=anchor.get('anchor_type') or dt(j['anchored_at'])!=dt(anchor['anchored_at']):raise ValueError('SRE_PLAN_ANCHOR_VERIFICATION_INVALID')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);ns=ap.parse_args();ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip);errors=[]
 if data.get('schema')!=INPUT_SCHEMA:errors.append('INPUT_SCHEMA_MISMATCH')
 pp,policy,e=exact(data.get('sre_policy_path'),data.get('sre_policy_sha256'),'SRE_POLICY_MISSING','SRE_POLICY_SHA_MISMATCH')
 if e:errors.append(e);policy={}
 elif policy.get('schema')!=POLICY_SCHEMA:errors.append('SRE_POLICY_SCHEMA_MISMATCH')
 try:
  registered=dt(policy['registered_at']);start=dt(policy['drill_start_at']);end=dt(policy['drill_end_at'])
  if registered>=start:errors.append('SRE_POLICY_NOT_REGISTERED_BEFORE_DRILL')
  if end<=start:errors.append('SRE_DRILL_WINDOW_INVALID')
  if policy.get('environment')!='STAGING':errors.append('SRE_REAL_DRILL_MUST_USE_STAGING')
  for k in ('max_rto_seconds','max_rpo_seconds','max_load_p95_ms','max_load_p99_ms','max_alert_delivery_seconds','max_chaos_recovery_seconds'):
   if float(policy[k])<=0:errors.append('SRE_POLICY_THRESHOLD_INVALID:'+k)
  if not 0<=float(policy['max_load_error_rate'])<1:errors.append('SRE_LOAD_ERROR_RATE_POLICY_INVALID')
  if float(policy['minimum_load_throughput_rps'])<=0:errors.append('SRE_LOAD_THROUGHPUT_POLICY_INVALID')
  required_chaos=set(policy['required_chaos_scenarios'])
  if not required_chaos:errors.append('SRE_CHAOS_SCENARIOS_REQUIRED')
  verify_plan_anchor(pp,data.get('plan_registration_anchor') or {},start,errors)
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc));start=end=None;required_chaos=set()

 bp,backup,e=exact(data.get('backup_manifest_path'),data.get('backup_manifest_sha256'),'BACKUP_MANIFEST_MISSING','BACKUP_MANIFEST_SHA_MISMATCH')
 if e:errors.append(e);backup={}
 elif backup.get('schema')!=BACKUP_SCHEMA or backup.get('result')!='PASS':errors.append('BACKUP_MANIFEST_NOT_PASS')
 try:
  if not bool(backup['immutable_backup']) or not bool(backup['encryption_verified']):errors.append('BACKUP_IMMUTABILITY_OR_ENCRYPTION_NOT_VERIFIED')
  if not valid_sha(backup['repository_tree_sha256']) or not valid_sha(backup['data_manifest_sha256']):errors.append('BACKUP_SOURCE_HASHES_REQUIRED')
  created=dt(backup['completed_at'])
  if start and created>start:errors.append('BACKUP_NOT_AVAILABLE_BEFORE_DRILL')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc));created=None

 rp,restore,e=exact(data.get('restore_evidence_path'),data.get('restore_evidence_sha256'),'RESTORE_EVIDENCE_MISSING','RESTORE_EVIDENCE_SHA_MISMATCH')
 if e:errors.append(e);restore={}
 elif restore.get('schema')!=RESTORE_SCHEMA or restore.get('result')!='PASS':errors.append('RESTORE_DRILL_NOT_PASS')
 rto=rpo=0.0
 try:
  rs=dt(restore['started_at']);re=dt(restore['completed_at']);last_data=dt(restore['last_recoverable_data_at'])
  if start and not(start<=rs<re<=end):errors.append('RESTORE_DRILL_OUTSIDE_WINDOW')
  if restore.get('backup_manifest_sha256')!=data.get('backup_manifest_sha256'):errors.append('RESTORE_BACKUP_BINDING_MISMATCH')
  if not bool(restore['real_restore_executed']):errors.append('REAL_RESTORE_REQUIRED')
  if restore['restored_repository_tree_sha256']!=backup.get('repository_tree_sha256') or restore['restored_data_manifest_sha256']!=backup.get('data_manifest_sha256'):errors.append('RESTORE_CONTENT_HASH_MISMATCH')
  if not bool(restore['application_boot_smoke_passed']) or not bool(restore['data_integrity_validation_passed']):errors.append('RESTORE_POST_VALIDATION_FAILED')
  rto=(re-rs).total_seconds();rpo=(rs-last_data).total_seconds()
  if abs(rto-float(restore['measured_rto_seconds']))>.001:errors.append('RTO_MEASUREMENT_MISMATCH')
  if abs(rpo-float(restore['measured_rpo_seconds']))>.001:errors.append('RPO_MEASUREMENT_MISMATCH')
  if rto>float(policy['max_rto_seconds']):errors.append('RTO_BREACH')
  if rpo>float(policy['max_rpo_seconds']):errors.append('RPO_BREACH')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

 lp,load,e=exact(data.get('load_test_evidence_path'),data.get('load_test_evidence_sha256'),'LOAD_TEST_EVIDENCE_MISSING','LOAD_TEST_EVIDENCE_SHA_MISMATCH')
 if e:errors.append(e);load={}
 elif load.get('schema')!=LOAD_SCHEMA or load.get('result')!='PASS':errors.append('LOAD_TEST_NOT_PASS')
 try:
  if float(load['p95_ms'])>float(policy['max_load_p95_ms']):errors.append('LOAD_P95_BREACH')
  if float(load['p99_ms'])>float(policy['max_load_p99_ms']):errors.append('LOAD_P99_BREACH')
  if float(load['error_rate'])>float(policy['max_load_error_rate']):errors.append('LOAD_ERROR_RATE_BREACH')
  if float(load['throughput_rps'])<float(policy['minimum_load_throughput_rps']):errors.append('LOAD_THROUGHPUT_INSUFFICIENT')
  if int(load['requests_total'])<int(policy['minimum_load_requests']):errors.append('LOAD_REQUEST_COUNT_INSUFFICIENT')
  if not bool(load['data_corruption_check_passed']):errors.append('LOAD_DATA_CORRUPTION_CHECK_FAILED')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

 cp,chaos,e=exact(data.get('chaos_test_evidence_path'),data.get('chaos_test_evidence_sha256'),'CHAOS_TEST_EVIDENCE_MISSING','CHAOS_TEST_EVIDENCE_SHA_MISMATCH')
 if e:errors.append(e);chaos={}
 elif chaos.get('schema')!=CHAOS_SCHEMA or chaos.get('result')!='PASS':errors.append('CHAOS_TEST_NOT_PASS')
 try:
  observed=set();
  for s in chaos['scenarios']:
   observed.add(str(s['scenario']))
   if not bool(s['safe_state_preserved']):errors.append('CHAOS_SAFE_STATE_NOT_PRESERVED:'+str(s['scenario']))
   if float(s['recovery_seconds'])>float(policy['max_chaos_recovery_seconds']):errors.append('CHAOS_RECOVERY_BREACH:'+str(s['scenario']))
   if int(s.get('orders_submitted',-1))!=0 or int(s.get('wagers_executed',-1))!=0:errors.append('CHAOS_WAGERING_ACTIVITY_FORBIDDEN:'+str(s['scenario']))
  missing=required_chaos-observed
  if missing:errors.append('CHAOS_SCENARIO_COVERAGE_MISSING:'+','.join(sorted(missing)))
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

 apath,alert,e=exact(data.get('alert_delivery_evidence_path'),data.get('alert_delivery_evidence_sha256'),'ALERT_EVIDENCE_MISSING','ALERT_EVIDENCE_SHA_MISMATCH')
 if e:errors.append(e);alert={}
 elif alert.get('schema')!=ALERT_SCHEMA or alert.get('result')!='PASS':errors.append('ALERT_DELIVERY_NOT_PASS')
 try:
  sent=dt(alert['sent_at']);delivered=dt(alert['delivered_at']);acked=dt(alert['acknowledged_at'])
  if not(sent<=delivered<=acked):errors.append('ALERT_TIMELINE_INVALID')
  latency=(delivered-sent).total_seconds()
  if latency>float(policy['max_alert_delivery_seconds']):errors.append('ALERT_DELIVERY_LATENCY_BREACH')
  if not str(alert['external_message_id']).strip() or not str(alert['delivery_channel']).strip():errors.append('ALERT_EXTERNAL_DELIVERY_PROOF_REQUIRED')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc));latency=0.0

 tp,tel,e=exact(data.get('telemetry_validation_evidence_path'),data.get('telemetry_validation_evidence_sha256'),'TELEMETRY_EVIDENCE_MISSING','TELEMETRY_EVIDENCE_SHA_MISMATCH')
 if e:errors.append(e);tel={}
 elif tel.get('schema')!=TELEMETRY_SCHEMA or tel.get('result')!='PASS':errors.append('TELEMETRY_VALIDATION_NOT_PASS')
 try:
  for k in ('trace_id_coverage','timestamp_coverage','stage_latency_coverage','error_code_coverage'):
   if float(tel[k])<float(policy['minimum_telemetry_field_coverage']):errors.append('TELEMETRY_COVERAGE_BREACH:'+k)
  if int(tel['schema_violations'])!=0:errors.append('TELEMETRY_SCHEMA_VIOLATIONS_PRESENT')
  if not valid_sha(tel['telemetry_schema_sha256']):errors.append('TELEMETRY_SCHEMA_SHA_REQUIRED')
 except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

 budgets=list(data.get('error_budget_evidence') or [])
 if not budgets:errors.append('ERROR_BUDGET_EVIDENCE_REQUIRED')
 budget_metrics=[]
 required_slos=set(policy.get('required_slos') or []);seen_slos=set()
 for b in budgets:
  try:
   name=str(b['slo_name']);seen_slos.add(name);total=int(b['total_events']);good=int(b['good_events']);target=float(b['target_fraction'])
   if total<1 or not 0<=good<=total or not 0<target<1:raise ValueError('ERROR_BUDGET_INPUT_INVALID')
   achieved=good/total;allowed=total*(1-target);bad=total-good;remaining=1-bad/allowed if allowed>0 else -1
   if achieved<target or remaining<float(policy['minimum_error_budget_remaining_fraction']):errors.append('ERROR_BUDGET_EXHAUSTED:'+name)
   budget_metrics.append({'slo_name':name,'achieved_fraction':achieved,'budget_remaining_fraction':remaining})
  except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))
 missing=required_slos-seen_slos
 if missing:errors.append('ERROR_BUDGET_SLO_COVERAGE_MISSING:'+','.join(sorted(missing)))

 passed=not errors
 out={'schema':SCHEMA,'result':'PASS' if passed else 'FAIL_CLOSED','running_auditor_path':str(Path(__file__).resolve()),'running_auditor_sha256':sha256(Path(__file__).resolve().read_bytes()).hexdigest(),'input_contract_sha256':INPUT_CONTRACT_SHA256,'input_path':str(ip),'input_sha256':fsha(ip),'metrics':{'measured_rto_seconds':rto,'measured_rpo_seconds':rpo,'alert_delivery_seconds':latency,'error_budgets':budget_metrics},'blocking_codes':sorted(set(errors)),'h03_real_sre_continuity_evidence_passed':passed,'real_restore_executed':bool(restore.get('real_restore_executed',False)),'orders_submitted':0,'wagers_executed':0,'controlled_live_admissible':False,'production_admissible':False,'output_payload_sha256':None}
 h=dict(out);h['output_payload_sha256']=None;out['output_payload_sha256']=canon(h);op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 print('RESULT='+('PASS' if passed else 'FAIL_CLOSED'));print('H03_REAL_SRE_CONTINUITY_EVIDENCE='+('PASS' if passed else 'FAIL'));print('REAL_RESTORE_EXECUTED='+str(bool(restore.get('real_restore_executed',False))).upper());print('BLOCKING_CODES='+(','.join(sorted(set(errors))) if errors else '<NONE>'));print('CONTROLLED_LIVE_ADMISSIBLE=FALSE');print('PRODUCTION_ADMISSIBLE=FALSE');print('EVIDENCE='+str(op));print('EVIDENCE_SHA256='+fsha(op));return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
