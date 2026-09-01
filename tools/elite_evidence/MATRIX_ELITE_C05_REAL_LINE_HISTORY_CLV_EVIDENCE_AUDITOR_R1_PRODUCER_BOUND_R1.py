from __future__ import annotations
import argparse,json
from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
from random import Random
from statistics import mean,median
from typing import Any

from matrix_elite.market_history import MarketLineHistory, odds_snapshot_sha256, probability_clv
from matrix_elite.odds import OddsSnapshot

SCHEMA='MATRIX_ELITE_C05_REAL_LINE_HISTORY_CLV_EVIDENCE_R1'
INPUT_CONTRACT_SHA256="e20c8bc074264603b0f3dc444079fa2f8e5d97122a3248c3fa589999ad1a0e29"

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
def pct(v,q):
    s=sorted(v); p=(len(s)-1)*q; lo=int(p); hi=min(lo+1,len(s)-1); f=p-lo; return s[lo]*(1-f)+s[hi]*f

def block_bootstrap_mean(values,*,block_length,bootstrap_samples,seed=505):
    n=len(values)
    if n<20 or block_length<1 or block_length>n or bootstrap_samples<1000: raise ValueError('CLV_BOOTSTRAP_CONFIGURATION_INVALID')
    starts=list(range(n-block_length+1)); rng=Random(seed); means=[]
    for _ in range(bootstrap_samples):
        idx=[]
        while len(idx)<n:
            st=starts[rng.randrange(len(starts))]; idx.extend(range(st,st+block_length))
        means.append(mean(values[i] for i in idx[:n]))
    return [pct(means,.025),pct(means,.975)]

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);ns=ap.parse_args();ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip)
    oos_path=Path(data['upstream_oos_evidence_path']).resolve();plan_path=Path(data['market_evidence_plan_path']).resolve();oos=readj(oos_path);plan=readj(plan_path);errors=[]
    if oos.get('schema') not in ('MATRIX_ELITE_C01_REAL_OOS_EVIDENCE_R2','MATRIX_ELITE_C01_REAL_OOS_EVIDENCE_R1') or oos.get('result')!='PASS' or oos.get('oos_edge_evidence_passed') is not True:errors.append('UPSTREAM_OOS_EVIDENCE_NOT_PASS')
    if data.get('upstream_oos_evidence_sha256')!=fsha(oos_path):errors.append('UPSTREAM_OOS_EVIDENCE_SHA_MISMATCH')
    if plan.get('schema')!='MATRIX_ELITE_C05_MARKET_EVIDENCE_PLAN_R1':errors.append('MARKET_EVIDENCE_PLAN_SCHEMA_MISMATCH')
    if data.get('market_evidence_plan_sha256')!=fsha(plan_path):errors.append('MARKET_EVIDENCE_PLAN_SHA_MISMATCH')
    sport=str(plan.get('sport',''));market=str(plan.get('market',''));competition=str(plan.get('competition',''))
    if (sport,competition,market)!=(str(oos.get('sport','')),str(oos.get('competition','')),str(oos.get('market',''))):errors.append('OOS_MARKET_SCOPE_MISMATCH')
    max_quote=timedelta(seconds=int(plan.get('max_quote_age_seconds',-1)));max_close=timedelta(seconds=int(plan.get('max_close_age_seconds',-1)));min_close=int(plan.get('minimum_closing_providers',0));min_decisions=int(plan.get('minimum_decisions',0));max_disadv=float(plan.get('max_price_disadvantage_fraction',-1));min_pos=float(plan.get('minimum_positive_clv_fraction',-1));require_ci=bool(plan.get('require_mean_clv_ci_above_zero',True));block_len=int(plan.get('block_length',0));bs=int(plan.get('bootstrap_samples',0))
    if max_quote.total_seconds()<0 or max_close.total_seconds()<0 or min_close<1 or min_decisions<20 or not 0<=max_disadv<=1 or not 0<=min_pos<=1 or block_len<1 or bs<1000:errors.append('MARKET_PLAN_CONFIGURATION_INVALID')
    selection_sets={str(k):tuple(str(x) for x in v) for k,v in (data.get('expected_selection_ids_by_market') or {}).items()}
    history=MarketLineHistory();snapshot_rows=data.get('market_snapshots') or [];groups={}
    for row in snapshot_rows:
        s=OddsSnapshot(event_id=str(row['event_id']),market_id=str(row['market_id']),selection_id=str(row['selection_id']),provider=str(row['provider']),captured_at=dt(row['captured_at']),decimal_odds=float(row['decimal_odds']),is_live=bool(row.get('is_live',False)))
        key=(s.event_id,s.market_id,s.provider,s.captured_at,s.is_live);groups.setdefault(key,[]).append(s)
    snapshot_hashes={}
    for key,ss in groups.items():
        expected=selection_sets.get(key[1])
        if not expected:errors.append('EXPECTED_SELECTION_SET_MISSING');continue
        try:snapshot_hashes['|'.join(map(str,key))]=history.add_complete_snapshot(ss,expected_selection_ids=expected)
        except ValueError as exc:errors.append(str(exc))
    decisions=[];clvs=[];price_disadvantages=[];actual_count=0;sim_count=0
    for d in data.get('decisions') or []:
        try:
            event=str(d['event_id']);mid=str(d['market_id']);sel=str(d['selection_id']);decision_at=dt(d['decision_at']);start=dt(d['event_start_at']);mp=float(d['model_probability']);mode=str(d['price_mode'])
            if decision_at>=start:raise ValueError('PREMATCH_DECISION_MUST_PRECEDE_EVENT_START')
            best=history.decision_state(event_id=event,market_id=mid,selection_id=sel,decision_at=decision_at,model_probability=mp,max_quote_age=max_quote,is_live=False)
            closing=history.prematch_closing_line(event_id=event,market_id=mid,selection_id=sel,event_start_at=start,max_close_age=max_close)
            if closing.providers_used<min_close:raise ValueError('MINIMUM_CLOSING_PROVIDERS_FAILED')
            if mode=='SIMULATED_BEST_AVAILABLE':taken_odds=best.decimal_odds;taken_provider=best.provider;taken_sha=best.quote_sha256;sim_count+=1
            elif mode=='ACTUAL_TAKEN':
                actual_count+=1;taken_odds=float(d['taken_decimal_odds']);taken_provider=str(d['taken_provider']);taken_at=dt(d['taken_captured_at']);taken_sha=str(d['taken_quote_sha256'])
                exact=None
                for row in snapshot_rows:
                    if str(row['event_id'])==event and str(row['market_id'])==mid and str(row['selection_id'])==sel and str(row['provider'])==taken_provider and dt(row['captured_at'])==taken_at and not bool(row.get('is_live',False)):
                        candidate=OddsSnapshot(event_id=event,market_id=mid,selection_id=sel,provider=taken_provider,captured_at=taken_at,decimal_odds=float(row['decimal_odds']),is_live=False)
                        if odds_snapshot_sha256(candidate)==taken_sha:exact=candidate;break
                if exact is None:raise ValueError('ACTUAL_TAKEN_QUOTE_HASH_BINDING_FAILED')
                if abs(exact.decimal_odds-taken_odds)>1e-12:raise ValueError('ACTUAL_TAKEN_ODDS_MISMATCH')
                age=decision_at-taken_at
                if age.total_seconds()<0:raise ValueError('ACTUAL_TAKEN_QUOTE_FROM_FUTURE')
                if age>max_quote:raise ValueError('ACTUAL_TAKEN_QUOTE_STALE')
            else:raise ValueError('PRICE_MODE_INVALID')
            disadv=max(0.0,(best.decimal_odds-taken_odds)/best.decimal_odds)
            if disadv>max_disadv:raise ValueError('PRICE_DISADVANTAGE_EXCEEDS_PLAN')
            clv=probability_clv(taken_decimal_odds=taken_odds,closing=closing);clvs.append(clv);price_disadvantages.append(disadv)
            decisions.append({'record_id':str(d['record_id']),'event_id':event,'market_id':mid,'selection_id':sel,'decision_at':decision_at.isoformat(),'event_start_at':start.isoformat(),'price_mode':mode,'taken_provider':taken_provider,'taken_decimal_odds':taken_odds,'taken_quote_sha256':taken_sha,'best_provider':best.provider,'best_decimal_odds':best.decimal_odds,'best_quote_sha256':best.quote_sha256,'price_disadvantage_fraction':disadv,'model_probability':mp,'expected_value_at_best':best.expected_value,'closing_consensus_fair_probability':closing.consensus_fair_probability,'closing_providers_used':closing.providers_used,'closing_latest_capture_at':closing.latest_provider_capture_at.isoformat(),'probability_clv':clv})
        except (ValueError,KeyError,TypeError) as exc:errors.append(str(exc))
    if len(decisions)<min_decisions:errors.append('MINIMUM_DECISIONS_FAILED')
    metrics={};ci=[None,None]
    if clvs:
        metrics={'n':len(clvs),'mean_probability_clv':mean(clvs),'median_probability_clv':median(clvs),'positive_clv_fraction':sum(1 for x in clvs if x>0)/len(clvs),'mean_price_disadvantage_fraction':mean(price_disadvantages),'actual_taken_count':actual_count,'simulated_best_available_count':sim_count}
        if len(clvs)>=20:
            try:ci=block_bootstrap_mean(clvs,block_length=block_len,bootstrap_samples=bs)
            except ValueError as exc:errors.append(str(exc))
        if metrics['positive_clv_fraction']<min_pos:errors.append('POSITIVE_CLV_FRACTION_BELOW_PLAN')
        if require_ci and (ci[0] is None or ci[0]<=0):errors.append('MEAN_CLV_CI_NOT_ABOVE_ZERO')
    passed=not errors
    out={'schema':SCHEMA,'result':'PASS' if passed else 'FAIL_CLOSED','running_auditor_path':str(Path(__file__).resolve()),'running_auditor_sha256':sha256(Path(__file__).resolve().read_bytes()).hexdigest(),'input_contract_sha256':INPUT_CONTRACT_SHA256,'input_path':str(ip),'input_sha256':fsha(ip),'upstream_oos_evidence_path':str(oos_path),'upstream_oos_evidence_sha256':fsha(oos_path),'market_evidence_plan_path':str(plan_path),'market_evidence_plan_sha256':fsha(plan_path),'sport':sport,'competition':competition,'market':market,'complete_snapshot_group_count':len(groups),'snapshot_hashes':snapshot_hashes,'decision_evidence':decisions,'metrics':metrics,'mean_clv_block_bootstrap_ci95':ci,'blocking_codes':sorted(set(errors)),'market_line_history_clv_evidence_passed':passed,'actual_execution_clv_proven':passed and actual_count==len(decisions) and actual_count>0,'automatic_wagering_authorized':False,'controlled_live_admissible':False,'production_admissible':False,'network_calls_performed':False,'output_payload_sha256':None}
    h=dict(out);h['output_payload_sha256']=None;out['output_payload_sha256']=canon(h);op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('RESULT='+('PASS' if passed else 'FAIL_CLOSED'));print('C05_REAL_LINE_HISTORY_CLV_EVIDENCE='+('PASS' if passed else 'FAIL'));print('DECISIONS='+str(len(decisions)));print('ACTUAL_EXECUTION_CLV_PROVEN='+str(out['actual_execution_clv_proven']).upper());print('BLOCKING_CODES='+(','.join(sorted(set(errors))) if errors else '<NONE>'));print('CONTROLLED_LIVE_ADMISSIBLE=FALSE');print('PRODUCTION_ADMISSIBLE=FALSE');print('EVIDENCE='+str(op));print('EVIDENCE_SHA256='+fsha(op));return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
