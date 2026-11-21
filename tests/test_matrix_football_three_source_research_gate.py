import pytest

from tools import matrix_football_three_source_research_gate as g


def fixtures():
    old={
        'schema':g.ORIG,'source_order':g.ORDER,'target_bogota_date':'2026-11-21',
        'captured_at_utc':'2026-11-17T02:08:15Z',
        'governance': {'canonical_model_input_authorized':False,'production_p_matrix_authorized':False,
            'telegram_signal_authorized':False,'automatic_wagering':False,
            'three_source_canonical_crosswalk_certified':False,'original_enriched_pit_equivalence_certified':False,'real_money':'BLOCKED'},
        'event': {'home':'Manchester City','away':'Fulham','source_provider_fixture_id':560643,
            'source_kickoff_utc':'2026-11-21T12:30:00Z',
            'sofascore':{'observed_event_id':'16363661','observed_event_url':'https://www.sofascore.com/es/football/match/fulham-manchester-city/rsT#id:16363661'},
            'flashscore':{'observed_event_url':'https://www.flashscore.co/partido/futbol/fulham-69ZiU2Om/manchester-city-Wtn9Stg0/'},
            'football_data_org':{'home':'Manchester City FC','away':'Fulham FC','kickoff_utc':'2026-11-21T12:30:00Z','provider_response_sha256':'a'*64}}}
    new={'schema':g.LATER,'source_order':g.ORDER,'target_date_bogota':'2026-11-21',
        'match':{'home':'Manchester City','away':'Fulham','sofascore_event_id':'16363661',
          'sofascore_url':'https://www.sofascore.com/es/football/match/fulham-manchester-city/rsT#id:16363661',
          'flashscore_mid':'MuVKeqEE','flashscore_mid_bearing_url':'https://www.flashscore.co/partido/futbol/fulham-69ZiU2Om/manchester-city-Wtn9Stg0/?mid=MuVKeqEE',
          'football_data_org_fixture_id':'560643','football_data_org_kickoff_utc':'2026-11-21T12:30:00Z',
          'browser_clock_timezone_independently_attested':False,'original_api_football_fixture_crosswalk_certified':False,
          'flashscore_current_page_display':'21.11.2026 07:30','displayed_clock_consistent_with_bogota_utc_minus_5':True},
        'admission':{'canonical_enriched_model_input_authorized':False,'production_p_matrix_authorized':False,
            'telegram_signal_authorized':False,'automatic_wagering':False,'real_money':'BLOCKED',
            'original_six_league_pit_equivalence_certified':False,'full_three_source_independent_event_identity_certified':False}}
    provider={'schema':g.PROOF,'football_named_competition_week_proof':{'verified':True,
        'response':{'http_status':200,'response_sha256':'a'*64},'model_admission_authorized':False,
        'historic_provider_id_equivalence_certified':False,
        'source_fixtures_research_only':[{'provider_fixture_id':560643,'home':'Manchester City FC','away':'Fulham FC','kickoff_utc':'2026-11-21T12:30:00Z'}]}}
    return old,new,provider


def test_read_only_fixture_consistency():
    report=g.verify(*fixtures())
    assert report['receipt_link_check_passed'] is True
    assert report['original_enriched_pit_certified'] is False
    assert report['browser_time_zone_independently_attested'] is False
    assert report['telegram_signal_authorized'] is False
    assert report['real_money']=='BLOCKED'

@pytest.mark.parametrize('tamper,code',[
    (lambda o,n,p: n['match'].__setitem__('sofascore_event_id','invalid'), 'SOFASCORE_ID_MISMATCH'),
    (lambda o,n,p: n['match'].__setitem__('flashscore_mid','2Nmg27Er'), 'FLASHSCORE_MID_LINK_MISMATCH'),
    (lambda o,n,p: n['match'].__setitem__('football_data_org_kickoff_utc','2026-11-21T13:30:00Z'), 'PROVIDER_KICKOFF_MISMATCH'),
    (lambda o,n,p: p['football_named_competition_week_proof']['source_fixtures_research_only'][0].__setitem__('home','Chelsea'), 'THIRD_SOURCE_TEAM_OR_TIME_MISMATCH'),
    (lambda o,n,p: n['admission'].__setitem__('production_p_matrix_authorized',True), 'UNAUTHORIZED_PROMOTION'),
    (lambda o,n,p: n['match'].__setitem__('browser_clock_timezone_independently_attested',True), 'OVERSTATED_CERTIFICATION'),
    (lambda o,n,p: o.__setitem__('source_order',['FLASHSCORE','SOFASCORE','FOOTBALL_DATA_ORG']), 'SOURCE_ORDER_MISMATCH'),
])
def test_fail_closed(tamper,code):
    documents=fixtures();tamper(*documents)
    with pytest.raises(ValueError,match=code):
        g.verify(*documents)
