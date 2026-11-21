"""Re-run exact 28-Oct archived Cup final matching without network or bets."""
import json
from pathlib import Path

from tools.matrix_13_cohort_espn_mls_results import compare

ROOT=Path(__file__).resolve().parents[1]
TRIAGE=ROOT/"evidence/governance/MATRIX_13_COHORT_ARCHIVED_FINAL_READINESS_LAST.json"
RAW=ROOT/"evidence/football_cohort_recovery"

def frozen(fid):
    data=json.loads(TRIAGE.read_text(encoding="utf-8"))
    return next(x for x in data["unsettled_fixture_triage"]
                if str(x["fixture_id"])==str(fid))

def payload(name):
    return json.loads((RAW/name).read_text(encoding="utf-8"))

def test_bayern_munchen_munich_is_unique_exact_ft_not_fuzzy():
    row=frozen("1638558")
    body=payload("ESPN_CUP_ger_dfb_pokal_20261028_RAW.json")
    matched,blocked=compare([row],body,"a"*64)
    assert not blocked and len(matched)==1
    assert matched[0]["espn_fixture_id"]=="401917035"
    assert (matched[0]["fulltime_home"],matched[0]["fulltime_away"])==(6,1)
    assert matched[0]["half_time_certified"] is False
    assert matched[0]["canonical_ledger_appends"]==0

def test_bournemouth_afc_prefix_is_unique_exact_ft():
    row=frozen("1640383")
    body=payload("ESPN_CUP_eng_league_cup_20261028_RAW.json")
    matched,blocked=compare([row],body,"b"*64)
    assert not blocked and len(matched)==1
    assert matched[0]["espn_fixture_id"]=="401921840"
    assert (matched[0]["fulltime_home"],matched[0]["fulltime_away"])==(3,0)
    assert matched[0]["telegram_authorized"] is False

def test_extra_time_and_penalties_stay_excluded_even_when_names_match():
    row=frozen("1640386") # Fleetwood Town vs Arsenal, penalties
    body=payload("ESPN_CUP_eng_league_cup_20261027_RAW.json")
    matched,blocked=compare([row],body,"c"*64)
    assert not matched
    assert blocked[0]["reason"]=="NO_UNIQUE_EXACT_ESPN_MATCH"

def test_wrong_start_never_joins_even_valid_club_alias():
    row=dict(frozen("1638558"))
    row["kickoff_utc"]="2026-10-28T19:46:00+00:00"
    matched,blocked=compare([row],payload("ESPN_CUP_ger_dfb_pokal_20261028_RAW.json"),"d"*64)
    assert not matched
    assert blocked[0]["reason"]=="NO_UNIQUE_EXACT_ESPN_MATCH"

def test_duplicate_same_event_is_not_admitted():
    row=frozen("1638558")
    body=payload("ESPN_CUP_ger_dfb_pokal_20261028_RAW.json")
    event=next(x for x in body["events"] if x["id"]=="401917035")
    body["events"].append(dict(event))
    matched,blocked=compare([row],body,"e"*64)
    assert not matched
    assert blocked[0]["reason"]=="NO_UNIQUE_EXACT_ESPN_MATCH"
