import pytest
from matrix_elite.live_slo import LiveTiming
from matrix_elite.live_validation import LiveValidationSample,LiveSLOPolicy,live_validation_report,live_slo_gate,grouped_live_reports


def timing(stage=10,window=200):
    return LiveTiming(stage,stage,stage,stage,stage,stage,stage,stage,window)

def sample(state='ENTRY',oracle=True,mode='SHADOW',stage=10,window=200,market='BTTS'):
    return LiveValidationSample('football',market,mode,timing(stage,window),state,oracle)

def policy(**kw):
    d=dict(minimum_samples=4,maximum_p95_ms=100,maximum_p99_ms=120,maximum_missed_window_rate=.1,maximum_stale_signal_rate=.1,maximum_decision_too_late_rate=.1,maximum_false_positive_rate=.2,maximum_false_negative_rate=.2,stale_threshold_ms=100,require_shadow=True);d.update(kw);return LiveSLOPolicy(**d)


def test_live_report_has_stage_and_end_to_end_percentiles():
    r=live_validation_report([sample() for _ in range(4)],stale_threshold_ms=100)
    assert r['p50_ms']==80 and r['p95_ms']==80 and r['stage_p95_ms']['feature_to_inference_ms']==10


def test_processing_latency_can_miss_open_window():
    r=live_validation_report([sample(window=50) for _ in range(4)],stale_threshold_ms=100)
    assert r['processing_missed_window_rate']==1 and r['decision_too_late_rate']==1


def test_window_already_closed_on_arrival_is_distinct_but_too_late():
    r=live_validation_report([sample(window=0) for _ in range(4)],stale_threshold_ms=100)
    assert r['window_closed_on_arrival_rate']==1 and r['processing_missed_window_rate']==0 and r['decision_too_late_rate']==1


def test_false_positive_and_false_negative_rates_are_explicit():
    rows=[sample('ENTRY',False),sample('ENTRY',True),sample('WATCH',True),sample('DISCARD',False)]
    r=live_validation_report(rows,stale_threshold_ms=100)
    assert r['false_positive_count']==1 and r['false_negative_count']==1
    assert r['false_positive_rate']==.5 and r['false_negative_rate']==.5


def test_slo_gate_passes_clean_shadow_sample():
    rows=[sample() for _ in range(4)]
    r=live_validation_report(rows,stale_threshold_ms=100)
    assert live_slo_gate(r,policy())['pass']


def test_slo_gate_requires_shadow_evidence():
    r=live_validation_report([sample(mode='REPLAY') for _ in range(4)],stale_threshold_ms=100)
    g=live_slo_gate(r,policy())
    assert not g['pass'] and 'SHADOW_EVIDENCE_REQUIRED' in g['reasons']


def test_slo_gate_blocks_false_negative_breach():
    rows=[sample('WATCH',True),sample('WATCH',True),sample('ENTRY',True),sample('ENTRY',True)]
    r=live_validation_report(rows,stale_threshold_ms=100)
    assert not live_slo_gate(r,policy(maximum_false_negative_rate=.1))['pass']


def test_slo_gate_blocks_latency_and_stale_breach():
    r=live_validation_report([sample(stage=20) for _ in range(4)],stale_threshold_ms=100)
    g=live_slo_gate(r,policy())
    assert not g['pass'] and 'P95_LATENCY_BREACH' in g['reasons'] and 'STALE_SIGNAL_RATE_BREACH' in g['reasons']


def test_grouped_reports_never_mix_markets():
    g=grouped_live_reports([sample(market='BTTS'),sample(market='TOTALS')],stale_threshold_ms=100)
    assert set(g)=={('football','BTTS'),('football','TOTALS')}


def test_negative_stage_latency_rejected_at_sample_construction():
    bad=LiveTiming(-1,1,1,1,1,1,1,1,100)
    with pytest.raises(ValueError,match='NEGATIVE_LATENCY'):
        LiveValidationSample('football','BTTS','SHADOW',bad,'ENTRY',True)
