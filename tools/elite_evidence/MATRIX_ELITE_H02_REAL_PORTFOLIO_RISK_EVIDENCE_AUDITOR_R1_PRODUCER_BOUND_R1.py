from __future__ import annotations
import argparse, json, math, random
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from statistics import mean
from typing import Any

SCHEMA='MATRIX_ELITE_H02_REAL_PORTFOLIO_RISK_EVIDENCE_R1'
INPUT_SCHEMA='MATRIX_ELITE_H02_REAL_PORTFOLIO_RISK_INPUT_R1'
INPUT_CONTRACT_SHA256="220f4af5a2317e5542f70058e1b694441207dc0f5c12cbed9650e98ac057f558"
POLICY_SCHEMA='MATRIX_ELITE_H02_PORTFOLIO_RISK_POLICY_R1'
CORR_SCHEMA='MATRIX_ELITE_H02_CORRELATION_CALIBRATION_EVIDENCE_R1'
KILL_SCHEMA='MATRIX_ELITE_H02_KILL_SWITCH_DRILL_EVIDENCE_R1'
PAPER_SCHEMAS={'MATRIX_ELITE_C02_REAL_PROSPECTIVE_PAPER_TRADING_EVIDENCE_R3'}


def dt(v:str)->datetime:
    x=datetime.fromisoformat(str(v).replace('Z','+00:00'))
    if x.tzinfo is None or x.utcoffset() is None: raise ValueError('TIME_MUST_BE_TIMEZONE_AWARE')
    return x

def readj(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8-sig'))
    if not isinstance(x,dict): raise ValueError('JSON_ROOT_MUST_BE_OBJECT')
    return x

def fsha(p:Path)->str:return sha256(p.read_bytes()).hexdigest()
def canon(x:Any)->str:return sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def valid_sha(v:Any)->bool:
    try:return isinstance(v,str) and len(v)==64 and int(v,16)>=0
    except Exception:return False

def exact_json(path_value:Any,sha_value:Any,missing:str,mismatch:str)->tuple[Path|None,dict[str,Any]|None,str|None]:
    try:
        p=Path(path_value).resolve()
        if not p.is_file():return None,None,missing
        if fsha(p)!=sha_value:return p,None,mismatch
        return p,readj(p),None
    except Exception:return None,None,missing

def record_hash(r:dict[str,Any])->str:
    return canon({'sequence':r['sequence'],'previous_record_sha256':r.get('previous_record_sha256'),'recorded_at':r['recorded_at'],'payload':r['payload']})

def verify_chain(records:list[dict[str,Any]],errors:list[str],label:str)->None:
    prev=None
    seen=set()
    for i,r in enumerate(records,1):
        try:
            if int(r['sequence'])!=i:raise ValueError(label+'_SEQUENCE_GAP_OR_REORDER')
            if r.get('previous_record_sha256')!=prev:raise ValueError(label+'_CHAIN_MISMATCH')
            h=record_hash(r)
            if r.get('record_sha256')!=h:raise ValueError(label+'_RECORD_HASH_MISMATCH')
            rid=str(r['payload']['risk_decision_id'])
            if rid in seen:raise ValueError(label+'_DUPLICATE_DECISION_ID')
            seen.add(rid);prev=h
        except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

def normal_cdf(z:float)->float:return 0.5*(1+math.erf(z/math.sqrt(2)))

def monte_carlo(positions:list[dict[str,Any]],trials:int,rho:float,seed:int)->dict[str,float]:
    rng=random.Random(seed);groups=sorted({str(p['correlation_group']) for p in positions});vals=[]
    for _ in range(trials):
        gz={g:rng.gauss(0,1) for g in groups};pnl=0.0
        for p in positions:
            z=math.sqrt(rho)*gz[str(p['correlation_group'])]+math.sqrt(1-rho)*rng.gauss(0,1)
            win=normal_cdf(z)<float(p['win_probability'])
            stake=float(p['stake_fraction']);odds=float(p['decimal_odds'])
            pnl+=stake*((odds-1) if win else -1)
        vals.append(pnl)
    vals.sort();n=len(vals)
    q=lambda x: vals[min(n-1,max(0,int((n-1)*x)))]
    return {'mean_pnl_fraction':sum(vals)/n,'p01_pnl_fraction':q(.01),'p05_pnl_fraction':q(.05),
            'probability_loss_20pct':sum(x<=-.20 for x in vals)/n,'probability_loss_40pct':sum(x<=-.40 for x in vals)/n,
            'worst_simulated_pnl_fraction':vals[0]}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);ns=ap.parse_args()
    ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip);errors=[]
    if data.get('schema')!=INPUT_SCHEMA:errors.append('INPUT_SCHEMA_MISMATCH')

    pp,policy,e=exact_json(data.get('risk_policy_path'),data.get('risk_policy_sha256'),'RISK_POLICY_MISSING','RISK_POLICY_SHA_MISMATCH')
    if e:errors.append(e);policy={}
    elif policy.get('schema')!=POLICY_SCHEMA:errors.append('RISK_POLICY_SCHEMA_MISMATCH')
    try:
        registered=dt(policy['registered_at']);start=dt(policy['evaluation_start_at']);end=dt(policy['evaluation_end_at'])
        if registered>=start:errors.append('RISK_POLICY_NOT_REGISTERED_BEFORE_EVALUATION')
        if end<=start:errors.append('RISK_EVALUATION_WINDOW_INVALID')
        for k in ('max_bet_fraction','max_event_fraction','max_day_fraction','max_group_fraction','max_probability_loss_20pct','max_probability_loss_40pct','max_actual_drawdown','max_daily_realized_loss_fraction','max_worst_group_loss_fraction','max_top2_group_loss_fraction'):
            if not 0<float(policy[k])<1:errors.append('RISK_POLICY_FRACTION_INVALID:'+k)
        rho=float(policy['stress_group_latent_correlation'])
        if not 0<=rho<1:errors.append('RISK_POLICY_CORRELATION_INVALID')
        trials=int(policy['stress_trials']);seed=int(policy['stress_seed'])
        if trials<5000:errors.append('RISK_STRESS_TRIALS_TOO_SMALL')
        if policy.get('stake_sizing')!='FRACTIONAL_KELLY_CAPPED':errors.append('RISK_STAKE_SIZING_POLICY_INVALID')
        kelly=float(policy['kelly_fraction'])
        if not 0<kelly<=0.25:errors.append('KELLY_FRACTION_EXCEEDS_MATRIX_GOVERNANCE')
        if bool(policy.get('chasing_losses_allowed')):errors.append('LOSS_CHASING_MUST_BE_FORBIDDEN')
    except (KeyError,TypeError,ValueError) as exc:
        errors.append(str(exc));start=end=None;rho=.99;trials=5000;seed=1

    # Real prospective paper evidence must be exact bound for each declared scope.
    paper_refs=list(data.get('paper_evidence') or [])
    if not paper_refs:errors.append('REAL_PAPER_EVIDENCE_REQUIRED')
    paper_scopes=set()
    for ref in paper_refs:
        p,j,e=exact_json(ref.get('path'),ref.get('sha256'),'PAPER_EVIDENCE_MISSING','PAPER_EVIDENCE_SHA_MISMATCH')
        if e:errors.append(e);continue
        if j.get('schema') not in PAPER_SCHEMAS or j.get('result')!='PASS' or j.get('paper_trading_evidence_passed') is not True:errors.append('PAPER_EVIDENCE_NOT_REAL_PASS');continue
        if j.get('performance_is_report_only_for_c02_gate') is not True:errors.append('PAPER_EVIDENCE_GOVERNANCE_MISMATCH')
        plan_path,plan_doc,pe=exact_json(j.get('paper_trading_plan_path'),j.get('paper_trading_plan_sha256'),'PAPER_PLAN_MISSING','PAPER_PLAN_SHA_MISMATCH')
        if pe:errors.append(pe);continue
        scope=(str(plan_doc.get('sport')),str(plan_doc.get('market')))
        if scope!=(str(ref.get('sport')),str(ref.get('market'))):errors.append('PAPER_EVIDENCE_SCOPE_REFERENCE_MISMATCH');continue
        paper_scopes.add(scope)

    cp,corr,e=exact_json(data.get('correlation_calibration_evidence_path'),data.get('correlation_calibration_evidence_sha256'),'CORRELATION_CALIBRATION_MISSING','CORRELATION_CALIBRATION_SHA_MISMATCH')
    if e:errors.append(e);corr={}
    elif corr.get('schema')!=CORR_SCHEMA or corr.get('result')!='PASS':errors.append('CORRELATION_CALIBRATION_NOT_PASS')
    try:
        if int(corr['sample_size'])<int(policy['minimum_correlation_calibration_samples']):errors.append('CORRELATION_CALIBRATION_SAMPLE_TOO_SMALL')
        upper=max(float(x['upper_ci']) for x in corr['groups'])
        if upper>rho:errors.append('STRESS_CORRELATION_BELOW_EMPIRICAL_UPPER_CI')
        if corr.get('method') not in {'BLOCK_BOOTSTRAP','HIERARCHICAL_BOOTSTRAP','SHRUNK_CORRELATION'}:errors.append('CORRELATION_METHOD_INVALID')
    except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

    decisions=list(data.get('risk_decision_records') or []);verify_chain(decisions,errors,'RISK_DECISION')
    if not decisions:errors.append('RISK_DECISIONS_REQUIRED')
    active=[];max_event=max_day=max_group=max_bet=0.0;day_exp=defaultdict(float);event_exp=defaultdict(float);group_exp=defaultdict(float)
    for rec in decisions:
        try:
            p=rec['payload'];at=dt(p['decided_at'])
            if start and not(start<=at<=end):raise ValueError('RISK_DECISION_OUTSIDE_EVALUATION_WINDOW')
            scope=(str(p['sport']),str(p['market_id']))
            if scope not in paper_scopes:raise ValueError('RISK_DECISION_SCOPE_LACKS_REAL_PAPER_EVIDENCE')
            for k in ('bet_id','event_id','market_id','correlation_group','day_id'):
                if not str(p.get(k,'')).strip():raise ValueError('RISK_DECISION_METADATA_REQUIRED')
            for k in ('data_snapshot_sha256','model_evidence_sha256','market_quote_sha256'):
                if not valid_sha(p.get(k)):raise ValueError('RISK_DECISION_REQUIRED_SHA_BINDING_MISSING')
            stake=float(p['stake_fraction']);prob=float(p['win_probability']);odds=float(p['decimal_odds'])
            if not 0<stake<1 or not 0<=prob<=1 or odds<=1:raise ValueError('RISK_DECISION_NUMERIC_INPUT_INVALID')
            day_key=str(p['day_id']);event_key=str(p['event_id']);group_key=str(p['correlation_group'])
            tentative_day=day_exp[day_key]+stake;tentative_event=event_exp[event_key]+stake;tentative_group=group_exp[group_key]+stake
            computed_pass=(stake<=float(policy['max_bet_fraction']) and tentative_event<=float(policy['max_event_fraction']) and tentative_day<=float(policy['max_day_fraction']) and tentative_group<=float(policy['max_group_fraction']))
            if bool(p['risk_gate_passed'])!=computed_pass:raise ValueError('RISK_DECISION_GATE_RESULT_MISMATCH')
            if bool(p['risk_gate_passed']):
                day_exp[day_key]=tentative_day;event_exp[event_key]=tentative_event;group_exp[group_key]=tentative_group
                max_bet=max(max_bet,stake);max_day=max(max_day,tentative_day);max_event=max(max_event,tentative_event);max_group=max(max_group,tentative_group)
                active.append({'stake_fraction':stake,'win_probability':prob,'decimal_odds':odds,'correlation_group':group_key})
        except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

    if max_bet>float(policy.get('max_bet_fraction',0)):errors.append('MAX_BET_CAP_BREACH_OBSERVED')
    if max_event>float(policy.get('max_event_fraction',0)):errors.append('MAX_EVENT_CAP_BREACH_OBSERVED')
    if max_day>float(policy.get('max_day_fraction',0)):errors.append('MAX_DAY_CAP_BREACH_OBSERVED')
    if max_group>float(policy.get('max_group_fraction',0)):errors.append('MAX_GROUP_CAP_BREACH_OBSERVED')

    stress={}
    if active:
        stress=monte_carlo(active,trials,rho,seed)
        if stress['probability_loss_20pct']>float(policy['max_probability_loss_20pct']):errors.append('TAIL_LOSS_20_PROBABILITY_BREACH')
        if stress['probability_loss_40pct']>float(policy['max_probability_loss_40pct']):errors.append('TAIL_LOSS_40_PROBABILITY_BREACH')
        group_losses=sorted((sum(x['stake_fraction'] for x in active if x['correlation_group']==g) for g in {x['correlation_group'] for x in active}),reverse=True)
        worst_group=group_losses[0] if group_losses else 0.0;top2=sum(group_losses[:2])
        if worst_group>float(policy['max_worst_group_loss_fraction']):errors.append('WORST_GROUP_SHOCK_BREACH')
        if top2>float(policy['max_top2_group_loss_fraction']):errors.append('TOP2_GROUP_SHOCK_BREACH')
    else:
        worst_group=top2=0.0;errors.append('NO_RISK_ACCEPTED_DECISIONS_TO_STRESS')

    # Real bankroll trace / actual kill thresholds.
    ledger=list(data.get('bankroll_ledger') or [])
    peak=None;max_dd=0.0;max_daily_loss=0.0
    last_time=None
    for row in ledger:
        try:
            at=dt(row['at']);bank=float(row['bankroll']);daily=float(row['daily_start_bankroll'])
            if bank<=0 or daily<=0:raise ValueError('BANKROLL_LEDGER_INVALID')
            if last_time and at<last_time:raise ValueError('BANKROLL_LEDGER_TIME_REORDER')
            last_time=at;peak=max(bank,peak or bank);dd=(peak-bank)/peak;dl=max(0,(daily-bank)/daily);max_dd=max(max_dd,dd);max_daily_loss=max(max_daily_loss,dl)
            expected_kill=dd>=float(policy['max_actual_drawdown']) or dl>=float(policy['max_daily_realized_loss_fraction']) or any(bool(row.get(k)) for k in ('data_incident','model_incident','execution_incident','provider_incident'))
            if bool(row['kill_switch_active'])!=expected_kill:raise ValueError('RUNTIME_KILL_SWITCH_STATE_MISMATCH')
            if expected_kill and int(row.get('new_positions_after_kill',0))!=0:raise ValueError('POSITIONS_OPENED_AFTER_KILL_SWITCH')
        except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))
    if not ledger:errors.append('REAL_BANKROLL_LEDGER_REQUIRED')

    # Independent kill-switch drills.
    drills=list(data.get('kill_switch_drills') or [])
    required={'DRAWDOWN','DAILY_LOSS','DATA_INCIDENT','MODEL_INCIDENT','EXECUTION_INCIDENT','PROVIDER_INCIDENT'};seen=set()
    for ref in drills:
        p,j,e=exact_json(ref.get('path'),ref.get('sha256'),'KILL_SWITCH_DRILL_MISSING','KILL_SWITCH_DRILL_SHA_MISMATCH')
        if e:errors.append(e);continue
        if j.get('schema')!=KILL_SCHEMA or j.get('result')!='PASS':errors.append('KILL_SWITCH_DRILL_NOT_PASS');continue
        typ=str(j.get('trigger_type'));seen.add(typ)
        if int(j.get('positions_opened_after_trigger',-1))!=0 or int(j.get('orders_submitted_after_trigger',-1))!=0:errors.append('KILL_SWITCH_DRILL_ALLOWED_POST_TRIGGER_ACTIVITY')
        if float(j.get('block_latency_ms',1e18))>float(policy.get('maximum_kill_switch_block_latency_ms',0)):errors.append('KILL_SWITCH_BLOCK_LATENCY_BREACH')
        if not valid_sha(j.get('audit_log_sha256')):errors.append('KILL_SWITCH_AUDIT_LOG_SHA_REQUIRED')
    missing=required-seen
    if missing:errors.append('KILL_SWITCH_DRILL_COVERAGE_MISSING:'+','.join(sorted(missing)))

    passed=not errors
    out={'schema':SCHEMA,'result':'PASS' if passed else 'FAIL_CLOSED','running_auditor_path':str(Path(__file__).resolve()),'running_auditor_sha256':sha256(Path(__file__).resolve().read_bytes()).hexdigest(),'input_contract_sha256':INPUT_CONTRACT_SHA256,'input_path':str(ip),'input_sha256':fsha(ip),
         'metrics':{'risk_decisions':len(decisions),'accepted_decisions':len(active),'max_bet_fraction':max_bet,'max_event_fraction':max_event,'max_day_fraction':max_day,'max_group_fraction':max_group,'max_actual_drawdown':max_dd,'max_daily_realized_loss_fraction':max_daily_loss,'worst_group_loss_fraction':worst_group,'top2_group_loss_fraction':top2,'stress':stress},
         'blocking_codes':sorted(set(errors)),'h02_real_portfolio_risk_evidence_passed':passed,
         'automatic_wagering_authorized':False,'controlled_live_admissible':False,'production_admissible':False,'output_payload_sha256':None}
    h=dict(out);h['output_payload_sha256']=None;out['output_payload_sha256']=canon(h)
    op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('RESULT='+('PASS' if passed else 'FAIL_CLOSED'));print('H02_REAL_PORTFOLIO_RISK_EVIDENCE='+('PASS' if passed else 'FAIL'));print('BLOCKING_CODES='+(','.join(sorted(set(errors))) if errors else '<NONE>'));print('CONTROLLED_LIVE_ADMISSIBLE=FALSE');print('PRODUCTION_ADMISSIBLE=FALSE');print('EVIDENCE='+str(op));print('EVIDENCE_SHA256='+fsha(op))
    return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
