from dataclasses import FrozenInstanceError
from datetime import datetime,timedelta,timezone
import pytest

from matrix_elite.paper_trading import ProspectivePaperDecision,PostEventReview,ProspectivePaperLedger

UTC=timezone.utc
T0=datetime(2026,1,1,tzinfo=UTC)
START=T0+timedelta(hours=2)

def decision(id='d1',action='PAPER_BET',prev=None):
    kwargs=dict(decision_id=id,sport='football',event_id='e',market_id='BTTS',selection_id='YES',decided_at=T0,event_start_at=START,action=action,model_version='m1',feature_version='f1',data_snapshot_sha256='a'*64,identity_manifest_sha256='b'*64,thesis_sha256='c'*64,decision_reason='pre-registered thesis',previous_decision_sha256=prev)
    if action=='PAPER_BET':kwargs.update(decimal_odds=2.0,price_provider='book',odds_snapshot_sha256='d'*64,matrix_probability=.55,fair_market_probability=.50,expected_value=.10,stake_units=1.0)
    return ProspectivePaperDecision(**kwargs)

def review(d,dsha,id='r1',prev=None,outcome='WIN',pnl=1.0):
    return PostEventReview(id,d.decision_id,dsha,d.event_start_at,START+timedelta(hours=3),outcome,pnl,'e'*64,'f'*64,.56,'MODEL_ERROR',('audit:1',),prev)


def test_paper_bet_requires_complete_price_probability_ev_and_stake():
    with pytest.raises(ValueError,match='PRICE_REQUIRED'):
        ProspectivePaperDecision('d','football','e','m','s',T0,START,'PAPER_BET','m','f','a'*64,'b'*64,'c'*64,'reason')


def test_no_bet_is_first_class_and_cannot_carry_stake():
    d=decision(action='NO_BET')
    assert d.action=='NO_BET' and d.stake_units==0
    with pytest.raises(ValueError,match='STAKE_MUST_BE_ZERO'):
        ProspectivePaperDecision(**{**d.__dict__,'stake_units':1})


def test_decision_must_be_frozen_before_event():
    with pytest.raises(ValueError,match='DECISION_NOT_PRE_EVENT'):
        ProspectivePaperDecision(**{**decision().__dict__,'decided_at':START})


def test_frozen_decision_is_immutable():
    d=decision()
    with pytest.raises(FrozenInstanceError):
        d.expected_value=.5


def test_decision_hash_chain_prevents_reordering_or_insertion():
    l=ProspectivePaperLedger();d1=decision();h1=l.append_decision(d1)
    with pytest.raises(ValueError,match='CHAIN_MISMATCH'):
        l.append_decision(decision('d2'))
    assert l.append_decision(decision('d2',prev=h1))


def test_review_requires_exact_frozen_decision_hash():
    l=ProspectivePaperLedger();d=decision();h=l.append_decision(d)
    with pytest.raises(ValueError,match='HASH_MISMATCH'):
        l.append_review(review(d,'0'*64))
    assert l.append_review(review(d,h))


def test_post_event_review_cannot_be_written_before_event():
    d=decision();h=d.sha256()
    with pytest.raises(ValueError,match='TOO_EARLY'):
        PostEventReview('r',d.decision_id,h,d.event_start_at,T0,'WIN',1,'e'*64,'f'*64,.55,'MODEL_ERROR',('evidence',))


def test_duplicate_review_is_rejected():
    l=ProspectivePaperLedger();d=decision();h=l.append_decision(d);r=review(d,h);l.append_review(r)
    with pytest.raises(ValueError,match='DUPLICATE_DECISION_REVIEW'):
        l.append_review(PostEventReview(**{**r.__dict__,'review_id':'r2','previous_review_sha256':r.sha256()}))


def test_no_bet_review_is_required_for_complete_opportunity_tracking():
    l=ProspectivePaperLedger();d=decision(action='NO_BET');h=l.append_decision(d)
    assert not l.completeness_report()['pass']
    r=review(d,h,outcome='NO_BET_OUTCOME',pnl=0);l.append_review(r)
    assert l.completeness_report()['pass'] and l.completeness_report()['no_bets']==1


def test_paper_performance_reports_yield_and_clv_without_rewriting_decision():
    l=ProspectivePaperLedger();d=decision();h=l.append_decision(d);l.append_review(review(d,h))
    p=l.performance_report()
    assert p['risked_units']==1 and p['pnl_units']==1 and p['yield']==1 and p['mean_probability_clv']>0


def test_variance_postmortem_requires_evidence():
    d=decision();h=d.sha256()
    with pytest.raises(ValueError,match='VARIANCE_REQUIRES_EVIDENCE'):
        PostEventReview('r',d.decision_id,h,d.event_start_at,START+timedelta(hours=3),'LOSS',-1,'e'*64,'f'*64,.5,'LEGITIMATE_VARIANCE',())
