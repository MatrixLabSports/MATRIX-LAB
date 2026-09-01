from __future__ import annotations
import argparse, json
from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256
from math import log
from pathlib import Path
from random import Random
from typing import Any, Sequence

from matrix_elite.baselines import (
    MARKETS_BY_SPORT, binary_baseline_benchmark, multiclass_baseline_benchmark,
    multiclass_brier_score, multiclass_log_loss, segment_stability_gate,
)
from matrix_elite.calibration import calibration_table, maximum_calibration_gap
from matrix_elite.metrics import brier_score, expected_calibration_error, log_loss
from matrix_elite.temporal_validation import (
    TemporalObservation, assert_no_tuning_on_holdout, final_chronological_holdout_indices,
    purged_expanding_walk_forward,
)
from matrix_elite.uncertainty import paired_moving_block_bootstrap_model_vs_market

SCHEMA='MATRIX_ELITE_C01_REAL_OOS_EVIDENCE_R2'
INPUT_CONTRACT_SHA256="8a1cc44511e3f0348a2a0c63a7b1b6ddf17eedc08a1a8abe956077b69c840657"
_EPS=1e-15

def dt(value: str) -> datetime:
    out=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if out.tzinfo is None or out.utcoffset() is None: raise ValueError('TIME_MUST_BE_TIMEZONE_AWARE')
    return out

def read_json(path: Path) -> dict[str,Any]:
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict): raise ValueError('JSON_ROOT_MUST_BE_OBJECT')
    return data

def file_sha(path: Path) -> str: return sha256(path.read_bytes()).hexdigest()

def canonical_sha(value: Any) -> str:
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()

def prob(x: Any) -> float:
    x=float(x)
    if not 0 <= x <= 1: raise ValueError('PROBABILITY_OUT_OF_RANGE')
    return x

def percentile(vals: list[float], q: float) -> float:
    v=sorted(vals); pos=(len(v)-1)*q; lo=int(pos); hi=min(lo+1,len(v)-1); f=pos-lo
    return v[lo]*(1-f)+v[hi]*f

def normalize_multiclass(row: Sequence[float], width: int) -> tuple[float,...]:
    if len(row)!=width: raise ValueError('MULTICLASS_WIDTH_MISMATCH')
    vals=tuple(prob(x) for x in row)
    if abs(sum(vals)-1.0)>1e-9: raise ValueError('MULTICLASS_PROBABILITIES_MUST_SUM_TO_ONE')
    return tuple(min(max(x,_EPS),1-_EPS) for x in vals)

def multiclass_block_bootstrap(model, market, outcomes, labels, *, block_length:int, bootstrap_samples:int, seed:int=836):
    n=len(outcomes)
    if not (len(model)==len(market)==n) or n<20: raise ValueError('MULTICLASS_BLOCK_BOOTSTRAP_N_AT_LEAST_20')
    if block_length<1 or block_length>n or bootstrap_samples<1000: raise ValueError('MULTICLASS_BOOTSTRAP_CONFIGURATION_INVALID')
    obs_b=multiclass_brier_score(market,outcomes,labels=labels)-multiclass_brier_score(model,outcomes,labels=labels)
    obs_l=multiclass_log_loss(market,outcomes,labels=labels)-multiclass_log_loss(model,outcomes,labels=labels)
    starts=list(range(0,n-block_length+1)); rng=Random(seed); bd=[]; ld=[]
    for _ in range(bootstrap_samples):
        idx=[]
        while len(idx)<n:
            st=starts[rng.randrange(len(starts))]; idx.extend(range(st,st+block_length))
        idx=idx[:n]
        m=[model[i] for i in idx]; x=[market[i] for i in idx]; y=[outcomes[i] for i in idx]
        bd.append(multiclass_brier_score(x,y,labels=labels)-multiclass_brier_score(m,y,labels=labels))
        ld.append(multiclass_log_loss(x,y,labels=labels)-multiclass_log_loss(m,y,labels=labels))
    return {'n':n,'block_length':block_length,'bootstrap_samples':bootstrap_samples,'brier_improvement':obs_b,'log_loss_improvement':obs_l,
            'brier_ci95':[percentile(bd,.025),percentile(bd,.975)],'log_loss_ci95':[percentile(ld,.025),percentile(ld,.975)]}

def multiclass_calibration(model, outcomes, labels, *, bins:int, minimum_bin_n:int):
    per_class={}; eces=[]; gaps=[]
    for j,label in enumerate(labels):
        ps=[row[j] for row in model]; ys=[1 if y==label else 0 for y in outcomes]
        e=expected_calibration_error(ps,ys,bins=bins)
        table=calibration_table(ps,ys,bins=bins,minimum_bin_n=minimum_bin_n)
        try: gap=maximum_calibration_gap(table)
        except ValueError: gap=1.0
        per_class[label]={'ece':e,'max_gap':gap,'powered_bins':sum(1 for b in table if b.n and not b.underpowered)}
        eces.append(e); gaps.append(gap)
    return {'macro_ece':sum(eces)/len(eces),'max_class_calibration_gap':max(gaps),'per_class':per_class}

def row_metric(problem_type, rows, labels=None):
    if problem_type=='BINARY':
        y=[int(r['outcome']) for r in rows]; mp=[r['model_p'] for r in rows]; xp=[r['market_p'] for r in rows]
        return {'n':len(rows),'model_brier':brier_score(mp,y),'market_brier':brier_score(xp,y),'model_log_loss':log_loss(mp,y),'market_log_loss':log_loss(xp,y),
                'brier_improvement':brier_score(xp,y)-brier_score(mp,y),'log_loss_improvement':log_loss(xp,y)-log_loss(mp,y)}
    y=[r['outcome'] for r in rows]; mp=[r['model_p'] for r in rows]; xp=[r['market_p'] for r in rows]
    return {'n':len(rows),'model_brier':multiclass_brier_score(mp,y,labels=labels),'market_brier':multiclass_brier_score(xp,y,labels=labels),
            'model_log_loss':multiclass_log_loss(mp,y,labels=labels),'market_log_loss':multiclass_log_loss(xp,y,labels=labels),
            'brier_improvement':multiclass_brier_score(xp,y,labels=labels)-multiclass_brier_score(mp,y,labels=labels),
            'log_loss_improvement':multiclass_log_loss(xp,y,labels=labels)-multiclass_log_loss(mp,y,labels=labels)}

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output',required=True); ns=ap.parse_args()
    ip=Path(ns.input).resolve(); op=Path(ns.output).resolve(); data=read_json(ip)
    upstream_path=Path(data['upstream_data_evidence_path']).resolve(); plan_path=Path(data['preregistered_plan_path']).resolve()
    upstream=read_json(upstream_path); plan=read_json(plan_path)
    registration_path=Path(data['plan_registration_path']).resolve(); registration=read_json(registration_path)
    evaluation_started=dt(data['evaluation_started_at_utc'])
    errors=[]
    if upstream.get('schema')!='MATRIX_ELITE_C03_C04_H04_REAL_DATA_EVIDENCE_R1' or upstream.get('result')!='PASS' or upstream.get('admitted') is not True: errors.append('UPSTREAM_DATA_EVIDENCE_NOT_ADMITTED')
    if data.get('upstream_data_evidence_sha256')!=file_sha(upstream_path): errors.append('UPSTREAM_DATA_EVIDENCE_SHA_MISMATCH')
    if plan.get('schema')!='MATRIX_ELITE_C01_OOS_PREREGISTERED_PLAN_R1': errors.append('PREREGISTERED_PLAN_SCHEMA_MISMATCH')
    plan_sha=file_sha(plan_path)
    if data.get('preregistered_plan_sha256')!=plan_sha: errors.append('PREREGISTERED_PLAN_SHA_MISMATCH')
    if registration.get('schema')!='MATRIX_ELITE_C01_OOS_PLAN_REGISTRATION_R1' or registration.get('plan_sha256')!=plan_sha: errors.append('PLAN_REGISTRATION_BINDING_INVALID')
    registered_at=dt(registration['registered_at_utc']) if registration.get('registered_at_utc') else None
    if registered_at is None or registered_at>evaluation_started: errors.append('PLAN_REGISTERED_AFTER_EVALUATION_START')
    evaluation_mode=str(plan.get('evaluation_mode',''))
    if evaluation_mode not in ('HISTORICAL_REPLAY','PROSPECTIVE'): errors.append('EVALUATION_MODE_INVALID')
    sport=str(plan.get('sport','')); competition=str(plan.get('competition','')); market=str(plan.get('market','')); problem_type=str(plan.get('problem_type',''))
    if sport not in MARKETS_BY_SPORT or market not in MARKETS_BY_SPORT.get(sport,set()): errors.append('SPORT_MARKET_NOT_REGISTERED')
    if problem_type not in ('BINARY','MULTICLASS'): errors.append('PROBLEM_TYPE_INVALID')
    us=upstream.get('scope') or {}
    if (sport,competition,market)!=(str(us.get('sport','')),str(us.get('competition','')),str(us.get('market',''))): errors.append('UPSTREAM_SCOPE_MISMATCH')
    labels=tuple(str(x) for x in (plan.get('labels') or []))
    if problem_type=='MULTICLASS' and (len(labels)<3 or len(set(labels))!=len(labels)): errors.append('MULTICLASS_LABELS_INVALID')

    # Configuration is preregistered and cannot be supplied ad hoc in the result input.
    min_train=int(plan.get('minimum_train',0)); validation_size=int(plan.get('validation_size',0)); holdout_size=int(plan.get('final_holdout_size',0)); embargo=timedelta(seconds=int(plan.get('embargo_seconds',0)))
    bootstrap_samples=int(plan.get('bootstrap_samples',0)); block_length=int(plan.get('block_length',0)); bins=int(plan.get('calibration_bins',0)); min_bin=int(plan.get('minimum_calibration_bin_n',0))
    max_ece=float(plan.get('max_ece',-1)); max_gap=float(plan.get('max_calibration_gap',-1)); min_segment_n=int(plan.get('minimum_segment_n',0)); min_seg_frac=float(plan.get('minimum_segment_positive_fraction',-1)); min_fold_frac=float(plan.get('minimum_fold_positive_fraction',-1)); max_quote_age=int(plan.get('max_market_quote_age_seconds',-1))
    if bootstrap_samples<1000: errors.append('BOOTSTRAP_SAMPLES_BELOW_1000')
    if min_train<20 or validation_size<20 or holdout_size<20 or block_length<1 or block_length>holdout_size: errors.append('OOS_SAMPLE_CONFIGURATION_INVALID')
    if bins<2 or min_bin<1 or not 0<=max_ece<=1 or not 0<=max_gap<=1 or min_segment_n<1 or not 0<min_seg_frac<=1 or not 0<min_fold_frac<=1 or max_quote_age<0: errors.append('OOS_THRESHOLD_CONFIGURATION_INVALID')

    rows=[]; raw_rows=data.get('prediction_rows') or []
    ids=set(); previous=None
    for idx,r in enumerate(raw_rows):
        rid=str(r['record_id']); decision=dt(r['decision_at']); target=dt(r['target_available_at']); generated=dt(r['prediction_generated_at']); feature_asof=dt(r['feature_snapshot_as_of_utc']); quote_at=dt(r['market_quote_observed_at'])
        if rid in ids: errors.append('DUPLICATE_RECORD_ID'); continue
        ids.add(rid)
        if previous is not None and decision<previous: errors.append('PREDICTION_ROWS_NOT_CHRONOLOGICAL')
        previous=decision
        if target<decision: errors.append('TARGET_AVAILABLE_BEFORE_DECISION')
        if evaluation_mode=='PROSPECTIVE' and generated>decision: errors.append('PREDICTION_GENERATED_AFTER_DECISION')
        if evaluation_mode=='HISTORICAL_REPLAY' and generated<evaluation_started: errors.append('REPLAY_PREDICTION_GENERATED_BEFORE_EVALUATION_START')
        if feature_asof>decision: errors.append('FEATURE_SNAPSHOT_AFTER_DECISION')
        age=(decision-quote_at).total_seconds()
        if age<0: errors.append('MARKET_QUOTE_FROM_FUTURE')
        if age>max_quote_age: errors.append('MARKET_QUOTE_STALE')
        fsha=str(r.get('feature_snapshot_sha256',''))
        try:
            if len(fsha)!=64: raise ValueError
            int(fsha,16)
        except Exception: errors.append('FEATURE_SNAPSHOT_SHA_INVALID')
        segment=str(r.get('segment','')).strip()
        if not segment: errors.append('SEGMENT_REQUIRED')
        if problem_type=='BINARY':
            y=int(r['outcome']);
            if y not in (0,1): errors.append('BINARY_OUTCOME_INVALID')
            model_p=prob(r['model_probability']); market_p=prob(r['market_probability'])
        else:
            y=str(r['outcome']);
            if y not in labels: errors.append('MULTICLASS_OUTCOME_INVALID')
            model_p=normalize_multiclass(r['model_probability'],len(labels)); market_p=normalize_multiclass(r['market_probability'],len(labels))
        rows.append({'record_id':rid,'decision':decision,'target':target,'model_p':model_p,'market_p':market_p,'outcome':y,'segment':segment})
    if len(rows)<min_train+validation_size+holdout_size: errors.append('TOTAL_SAMPLE_TOO_SMALL')
    if rows:
        plan_created=dt(plan['created_at_utc'])
        if plan_created>evaluation_started: errors.append('PLAN_CREATED_AFTER_EVALUATION_START')
        if evaluation_mode=='PROSPECTIVE' and plan_created>=rows[0]['decision']: errors.append('PROSPECTIVE_PLAN_NOT_CREATED_BEFORE_FIRST_DECISION')
    if str(plan.get('model_version','')).strip()!=str(data.get('model_version','')).strip(): errors.append('MODEL_VERSION_MISMATCH')
    if str(plan.get('feature_version','')).strip()!=str(data.get('feature_version','')).strip(): errors.append('FEATURE_VERSION_MISMATCH')

    folds=[]; fold_metrics=[]; fold_positive_fraction=0.0; holdout_ids=[]; holdout_metrics={}; calibration={}; bootstrap={}; baseline={}; segment_gate={}; final_holdout_untouched=False
    if not errors:
        tune_idx, hold_idx=final_chronological_holdout_indices(len(rows),holdout_size=holdout_size)
        holdout_ids=[rows[i]['record_id'] for i in hold_idx]
        tuning_ids=set(str(x) for x in (data.get('tuning_record_ids') or []))
        if not tuning_ids: errors.append('TUNING_RECORD_IDS_REQUIRED')
        try: assert_no_tuning_on_holdout(tuning_indices=[i for i,r in enumerate(rows) if r['record_id'] in tuning_ids],holdout_indices=hold_idx); final_holdout_untouched=True
        except ValueError: errors.append('FINAL_HOLDOUT_TOUCHED_BY_TUNING')
        if any(rows[i]['record_id'] not in tuning_ids for i in tune_idx): errors.append('TUNING_RECORD_IDS_DO_NOT_COVER_PREHOLDOUT')
        observations=[TemporalObservation(r['decision'],r['target']) for r in rows[:hold_idx[0]]]
        try: folds=purged_expanding_walk_forward(observations,min_train=min_train,validation_size=validation_size,embargo=embargo)
        except ValueError as exc: errors.append(str(exc))
        for f in folds:
            vr=[rows[i] for i in f.validation_indices]
            met=row_metric(problem_type,vr,labels=labels if problem_type=='MULTICLASS' else None); met['validation_start_utc']=f.validation_start.isoformat(); met['train_n']=len(f.train_indices)
            met['positive_both']=met['brier_improvement']>0 and met['log_loss_improvement']>0; fold_metrics.append(met)
        fold_positive_fraction=(sum(1 for x in fold_metrics if x['positive_both'])/len(fold_metrics)) if fold_metrics else 0.0
        if fold_positive_fraction<min_fold_frac: errors.append('WALK_FORWARD_FOLD_STABILITY_FAILED')
        train_rows=[rows[i] for i in tune_idx]; hold=[rows[i] for i in hold_idx]
        holdout_metrics=row_metric(problem_type,hold,labels=labels if problem_type=='MULTICLASS' else None)
        if problem_type=='BINARY':
            train_y=[r['outcome'] for r in train_rows]; hy=[r['outcome'] for r in hold]; hm=[r['model_p'] for r in hold]; hx=[r['market_p'] for r in hold]
            b=binary_baseline_benchmark(train_outcomes=train_y,validation_outcomes=hy,validation_market_probabilities=hx); baseline={'empirical_probability':b.empirical_probability,'empirical_brier':b.empirical_brier,'empirical_log_loss':b.empirical_log_loss,'market_brier':b.market_brier,'market_log_loss':b.market_log_loss}
            tab=calibration_table(hm,hy,bins=bins,minimum_bin_n=min_bin); ece=expected_calibration_error(hm,hy,bins=bins)
            try: gap=maximum_calibration_gap(tab)
            except ValueError: gap=1.0
            calibration={'ece':ece,'max_calibration_gap':gap,'powered_bins':sum(1 for x in tab if x.n and not x.underpowered),'bins_total':len(tab)}
            bb=paired_moving_block_bootstrap_model_vs_market(hm,hx,hy,block_length=block_length,bootstrap_samples=bootstrap_samples); bootstrap={'n':bb.n,'block_length':bb.block_length,'bootstrap_samples':bb.bootstrap_samples,'brier_improvement':bb.brier_improvement,'log_loss_improvement':bb.log_loss_improvement,'brier_ci95':list(bb.brier_ci95),'log_loss_ci95':list(bb.log_loss_ci95)}
        else:
            train_y=[r['outcome'] for r in train_rows]; hy=[r['outcome'] for r in hold]; hm=[r['model_p'] for r in hold]; hx=[r['market_p'] for r in hold]
            b=multiclass_baseline_benchmark(train_outcomes=train_y,validation_outcomes=hy,validation_market_probabilities=hx,labels=labels); baseline={'labels':list(b.labels),'empirical_probabilities':list(b.empirical_probabilities),'empirical_brier':b.empirical_brier,'empirical_log_loss':b.empirical_log_loss,'market_brier':b.market_brier,'market_log_loss':b.market_log_loss}
            calibration=multiclass_calibration(hm,hy,labels,bins=bins,minimum_bin_n=min_bin)
            bootstrap=multiclass_block_bootstrap(hm,hx,hy,labels,block_length=block_length,bootstrap_samples=bootstrap_samples)
        ece_value=calibration['ece'] if problem_type=='BINARY' else calibration['macro_ece']; gap_value=calibration['max_calibration_gap'] if problem_type=='BINARY' else calibration['max_class_calibration_gap']
        if ece_value>max_ece: errors.append('MODEL_ECE_EXCEEDS_PREREGISTERED_LIMIT')
        if gap_value>max_gap: errors.append('CALIBRATION_GAP_EXCEEDS_PREREGISTERED_LIMIT')
        if bootstrap['brier_improvement']<=0 or bootstrap['log_loss_improvement']<=0: errors.append('MODEL_DOES_NOT_BEAT_MARKET_POINT_ESTIMATE')
        if bootstrap['brier_ci95'][0]<=0 or bootstrap['log_loss_ci95'][0]<=0: errors.append('MODEL_EDGE_CI_NOT_ABOVE_ZERO')
        seg=defaultdict(list)
        for r in hold: seg[r['segment']].append(r)
        seg_metrics={}
        for name,rs in sorted(seg.items()):
            met=row_metric(problem_type,rs,labels=labels if problem_type=='MULTICLASS' else None); seg_metrics[name]=(met['n'],met['brier_improvement'],met['log_loss_improvement'])
        segment_gate=segment_stability_gate(seg_metrics,minimum_segment_n=min_segment_n,minimum_positive_segment_fraction=min_seg_frac)
        segment_gate['segments']={k:{'n':v[0],'brier_improvement':v[1],'log_loss_improvement':v[2]} for k,v in seg_metrics.items()}
        if not segment_gate['pass']: errors.append('SEGMENT_STABILITY_FAILED')

    passed=not errors
    output={
      'schema':SCHEMA,'result':'PASS' if passed else 'FAIL_CLOSED','running_auditor_path':str(Path(__file__).resolve()),'running_auditor_sha256':sha256(Path(__file__).resolve().read_bytes()).hexdigest(),'input_contract_sha256':INPUT_CONTRACT_SHA256,
      'input_path':str(ip),'input_sha256':file_sha(ip),'upstream_data_evidence_path':str(upstream_path),'upstream_data_evidence_sha256':file_sha(upstream_path),
      'preregistered_plan_path':str(plan_path),'preregistered_plan_sha256':file_sha(plan_path),'plan_registration_path':str(registration_path),'plan_registration_sha256':file_sha(registration_path),'evaluation_started_at_utc':evaluation_started.isoformat(),'evaluation_mode':evaluation_mode,'sport':sport,'competition':competition,'market':market,'problem_type':problem_type,
      'model_version':str(data.get('model_version','')),'feature_version':str(data.get('feature_version','')),'n':len(rows),'fold_count':len(folds),'fold_positive_fraction':fold_positive_fraction,
      'fold_metrics':fold_metrics,'final_holdout_n':len(holdout_ids),'final_holdout_record_ids':holdout_ids,'final_holdout_untouched':final_holdout_untouched,
      'holdout_metrics':holdout_metrics,'empirical_and_market_baselines':baseline,'calibration':calibration,'block_bootstrap_vs_market':bootstrap,'segment_stability':segment_gate,
      'blocking_codes':sorted(set(errors)),'oos_edge_evidence_passed':passed,'automatic_model_promotion_authorized':False,'wagering_authorized':False,
      'controlled_live_admissible':False,'production_admissible':False,'network_calls_performed':False,'output_payload_sha256':None,
    }
    h=dict(output); h['output_payload_sha256']=None; output['output_payload_sha256']=canonical_sha(h)
    op.parent.mkdir(parents=True,exist_ok=True); op.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('RESULT='+('PASS' if passed else 'FAIL_CLOSED')); print('C01_REAL_OOS_EVIDENCE='+('PASS' if passed else 'FAIL')); print('EVALUATION_MODE='+evaluation_mode); print('OOS_EDGE_EVIDENCE_PASSED='+str(passed).upper()); print('FOLD_COUNT='+str(len(folds))); print('FINAL_HOLDOUT_N='+str(len(holdout_ids))); print('BLOCKING_CODES='+(','.join(sorted(set(errors))) if errors else '<NONE>')); print('AUTOMATIC_MODEL_PROMOTION_AUTHORIZED=FALSE'); print('CONTROLLED_LIVE_ADMISSIBLE=FALSE'); print('PRODUCTION_ADMISSIBLE=FALSE'); print('EVIDENCE='+str(op)); print('EVIDENCE_SHA256='+file_sha(op))
    return 0 if passed else 2

if __name__=='__main__': raise SystemExit(main())
