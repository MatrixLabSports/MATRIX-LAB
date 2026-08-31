import pytest
from matrix_elite.failover import ProviderHealth
from matrix_elite.portfolio_risk import RiskBet,PortfolioRiskPolicy,RuntimeRiskState,monte_carlo_portfolio_stress,portfolio_risk_gate,runtime_kill_switch
from matrix_elite.provider_redundancy import reconcile_provider_snapshots,governed_failover_with_reconciliation


def bet(id,event='e',group='g',stake=.02,p=.55,odds=2.0):return RiskBet(id,'football',event,'BTTS',group,stake,p,odds)
def policy(**kw):
 d=dict(max_bet_fraction=.03,max_event_fraction=.05,max_day_fraction=.10,max_group_fraction=.05,max_group_latent_correlation=.25,max_probability_loss_20pct=.05,max_probability_loss_40pct=.01,max_actual_drawdown=.20,max_daily_realized_loss_fraction=.08);d.update(kw);return PortfolioRiskPolicy(**d)


def test_monte_carlo_stress_is_deterministic_and_reports_tails():
    bets=[bet('1'),bet('2',event='e2',group='g2')]
    a=monte_carlo_portfolio_stress(bets,trials=2000,seed=7);b=monte_carlo_portfolio_stress(bets,trials=2000,seed=7)
    assert a==b and 'probability_loss_20pct' in a and 'p01_pnl_fraction' in a


def test_portfolio_risk_gate_blocks_event_and_group_concentration():
    bets=[bet('1',stake=.03),bet('2',stake=.03)]
    g=portfolio_risk_gate(bets,policy=policy(),trials=1000,seed=1)
    assert not g['pass'] and 'EVENT_CAP_BREACH' in g['reasons'] and 'GROUP_CAP_BREACH' in g['reasons']


def test_portfolio_risk_gate_can_pass_small_diversified_positions():
    bets=[bet('1',event='e1',group='g1',stake=.01),bet('2',event='e2',group='g2',stake=.01)]
    assert portfolio_risk_gate(bets,policy=policy(max_probability_loss_20pct=.2,max_probability_loss_40pct=.1),trials=1000,seed=1)['pass']


def test_kill_switch_blocks_drawdown_daily_loss_and_incidents():
    s=RuntimeRiskState(80,100,90,data_incident=True)
    k=runtime_kill_switch(s,policy=policy())
    assert k['kill'] and 'MAX_DRAWDOWN_KILL' in k['reasons'] and 'DAILY_LOSS_KILL' in k['reasons'] and 'DATA_INCIDENT_KILL' in k['reasons']


def test_provider_reconciliation_measures_overlap_disagreement_and_missing():
    r=reconcile_provider_snapshots({'a':'1','b':'2'},{'a':'1','b':'x','c':'3'})
    assert r.keys_overlap==2 and r.disagreement_count==1 and r.missing_primary_count==1 and r.disagreement_rate_on_overlap==.5


def test_failover_never_switches_without_human_approval():
    p=ProviderHealth('p',.5,False,True,True);s=ProviderHealth('s',1,True,True,True);r=reconcile_provider_snapshots({'a':'1'},{'a':'1'})
    with pytest.raises(ValueError,match='AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN'):
        governed_failover_with_reconciliation(p,s,reconciliation=r,minimum_secondary_coverage=.9,minimum_overlap_rate=.9,maximum_disagreement_rate=.05,human_approved=False,approval_evidence_sha256=None)


def test_failover_requires_evidence_and_low_disagreement():
    p=ProviderHealth('p',.5,False,True,True);s=ProviderHealth('s',1,True,True,True)
    good=reconcile_provider_snapshots({'a':'1','b':'2'},{'a':'1','b':'2'})
    with pytest.raises(ValueError,match='APPROVAL_EVIDENCE_REQUIRED'):
        governed_failover_with_reconciliation(p,s,reconciliation=good,minimum_secondary_coverage=.9,minimum_overlap_rate=.9,maximum_disagreement_rate=.05,human_approved=True,approval_evidence_sha256=None)
    bad=reconcile_provider_snapshots({'a':'1','b':'2'},{'a':'x','b':'y'})
    with pytest.raises(ValueError,match='DISAGREEMENT_TOO_HIGH'):
        governed_failover_with_reconciliation(p,s,reconciliation=bad,minimum_secondary_coverage=.9,minimum_overlap_rate=.9,maximum_disagreement_rate=.05,human_approved=True,approval_evidence_sha256='a'*64)
    assert governed_failover_with_reconciliation(p,s,reconciliation=good,minimum_secondary_coverage=.9,minimum_overlap_rate=.9,maximum_disagreement_rate=.05,human_approved=True,approval_evidence_sha256='a'*64)=='s'


def test_healthy_primary_is_retained_without_switch():
    p=ProviderHealth('p',1,True,True,True);s=ProviderHealth('s',1,True,True,True);r=reconcile_provider_snapshots({'a':'1'},{'a':'1'})
    assert governed_failover_with_reconciliation(p,s,reconciliation=r,minimum_secondary_coverage=.9,minimum_overlap_rate=.9,maximum_disagreement_rate=.05,human_approved=False,approval_evidence_sha256=None)=='p'
