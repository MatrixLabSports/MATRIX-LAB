"""Strict, entirely mocked contract tests for independent quotes (no API spending)."""
from datetime import datetime,timedelta,timezone
from tools.matrix_independent_over25_quote_audit import audit,_price_rows,match_event

NOW=datetime(2026,11,2,16,30,tzinfo=timezone.utc)

def intake():
    return {"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
            "target_date_bogota":"2026-11-02","real_money":"BLOCKED",
            "signal_generation_authorized":False,"fixtures":[{
                "source_fixture_id":"558541","home":"US Sassuolo Calcio",
                "away":"ACF Fiorentina","kickoff_utc":"2026-11-02T17:30:00+00:00"}]}
def scores():
    return {"schema":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
            "target_date_bogota":"2026-11-02","real_money":"BLOCKED",
            "market_signal_authorized":False,"scored":[{
                "source_fixture_id":"558541","kickoff_utc":"2026-11-02T17:30:00+00:00",
                "p_over25_research":0.68}]}
class Response:
    def __init__(self,payload,status=200):
        self.status_code=status;self.payload=payload
    def json(self):return self.payload
class Fake:
    def __init__(self,usage=None,stale=False,include_sharp=True):
        self.calls=[];self.usage=usage or {"api_credits_used":20,"api_credits_limit":100}
        self.stale=stale;self.include_sharp=include_sharp
    def get(self,url,headers=None,params=None,timeout=None):
        assert headers["X-API-Key"]=="test-secret"
        self.calls.append(url)
        if url.endswith("/usage"):return Response(self.usage)
        if url.endswith("/events"):
            return Response({"items":[{"event_id":"match-1","home_team":"US Sassuolo Calcio","away_team":"ACF Fiorentina"}]})
        if url.endswith("/odds/snapshot"):
            age=121 if self.stale else 30
            ts=int((NOW-timedelta(seconds=age)).timestamp()*1000)
            rows=[{"bookmaker":"betano","market_key":"total","bet_type":"total",
                   "period_str":"full time","side":"over","line":2.5,
                   "odds":1.9,"is_available":True}]
            if self.include_sharp:
                rows.append({"bookmaker":"pinnacle","market_key":"total","bet_type":"total",
                             "period_str":"full time","side":"over","line":2.5,
                             "odds":1.82,"is_available":True})
            return Response({"bookmaker_as_of_ts_ms":{"betano":ts,"pinnacle":ts},"items":rows})
        raise AssertionError(url)

def test_verified_exact_quotes_remain_research_only_no_telegram():
    s=Fake()
    r=audit(intake(),scores(),"test-secret",session=s,now=NOW)
    assert len(s.calls)==3
    assert r["independent_match_count"]==1
    assert r["bookmaker_quote_verified_count"]==1
    assert r["sharp_120s_verified_count"]==1
    assert r["audited"][0]["research_quality_gate_pass"] is True
    assert r["audited"][0]["research_ev"]>0
    assert r["signal_generation_authorized"] is False
    assert r["telegram_messages_sent"]==0
    assert r["production_calibration_parity_verified"] is False
    assert r["real_money"]=="BLOCKED"

def test_exhausted_monthly_quota_blocks_events_and_snapshots():
    s=Fake(usage={"api_credits_used":100,"api_credits_limit":100,"exceeded":True})
    r=audit(intake(),scores(),"test-secret",session=s,now=NOW)
    assert r["quota_status"]=="BLOCKED_EXHAUSTED"
    assert r["network_calls"]==1
    assert s.calls==["https://api.odds-api.net/v1/usage"]
    assert r["signal_generation_authorized"] is False

def test_stale_quote_cannot_count_as_fresh():
    s=Fake(stale=True)
    r=audit(intake(),scores(),"test-secret",session=s,now=NOW)
    assert r["bookmaker_quote_verified_count"]==0
    assert r["sharp_120s_verified_count"]==0
    assert r["audited"][0]["quotes"]==[]

def test_reference_only_never_counts_as_colombia_quote():
    s=Fake(include_sharp=False)
    r=audit(intake(),scores(),"test-secret",session=s,now=NOW)
    assert r["bookmaker_quote_verified_count"]==1
    assert r["sharp_120s_verified_count"]==0
    assert r["audited"][0]["identity_status"]!="RESEARCH_QUOTE_PAIRED_NO_CALIBRATION_PARITY"

def test_rejects_ambiguous_team_pairs():
    f=intake()["fixtures"][0]
    e={"event_id":"1","home_team":"US Sassuolo Calcio","away_team":"ACF Fiorentina"}
    event,status=match_event(f,[e,dict(e,event_id="2")])
    assert event is None
    assert status=="AMBIGUOUS_PROVIDER_EVENT_IDENTITY"

def test_rejects_non_full_time_or_non_2_5_and_unavailable():
    ts=int((NOW-timedelta(seconds=4)).timestamp()*1000)
    snap={"bookmaker_as_of_ts_ms":{"betano":ts},"items":[
         {"bookmaker":"betano","market_key":"total","bet_type":"total","period_str":"first half","side":"over","line":2.5,"odds":1.9,"is_available":True},
         {"bookmaker":"betano","market_key":"total","bet_type":"total","period_str":"full time","side":"over","line":3.5,"odds":1.9,"is_available":True},
         {"bookmaker":"betano","market_key":"total","bet_type":"total","period_str":"full time","side":"over","line":2.5,"odds":1.9,"is_available":False}]}
    assert _price_rows(snap,NOW)==[]

def test_no_sharp_or_model_parity_can_authorize_telegram():
    s=Fake()
    r=audit(intake(),scores(),"test-secret",session=s,now=NOW)
    assert r["audited"][0]["identity_status"]=="RESEARCH_QUOTE_PAIRED_NO_CALIBRATION_PARITY"
    assert all(v is False for v in (
       r["provider_source_equivalence_verified"],
       r["browser_first_reconciliation_verified"],
       r["production_calibration_parity_verified"],
       r["signal_generation_authorized"]
    ))

def test_out_of_window_never_contacts_pricing_endpoint():
    s=Fake()
    r=audit(intake(),scores(),"test-secret",session=s,now=NOW-timedelta(hours=8))
    assert r["network_calls"]==0
    assert r["quota_status"]=="SKIPPED_NO_PREMATCH_WINDOW"
    assert s.calls==[]
