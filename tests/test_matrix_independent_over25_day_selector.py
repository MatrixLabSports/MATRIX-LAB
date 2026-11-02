from datetime import datetime, timezone
from pathlib import Path
import json

from tools.matrix_independent_over25_day_selector import choose

def t(text):
    return datetime.fromisoformat(text.replace("Z","+00:00")).astimezone(timezone.utc)

def add(root: Path, date: str, fid: str, utc_kickoff: str, **kw):
    folder = root / date
    folder.mkdir(parents=True,exist_ok=True)
    intake = {"schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
              "target_date_bogota":date,
              "source_order":["SOFASCORE","FLASHSCORE","APIS"],
              "real_money":"BLOCKED","signal_generation_authorized":False,
              "fixtures":[{"source_fixture_id":fid,"kickoff_utc":utc_kickoff}]}
    shadow = {"schema":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
              "target_date_bogota":date,
              "real_money":"BLOCKED","market_signal_authorized":False,
              "parameter_refit":False,"odds_used_to_generate_probability":False,
              "scored":[{"source_fixture_id":fid,"kickoff_utc":utc_kickoff}]}
    browser = {"schema":"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK_V1",
               "target_date_bogota":date,
               "source_order":["SOFASCORE","FLASHSCORE","APIS"],
               "real_money":"BLOCKED","signal_generation_authorized":False,
               "status":"PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL",
               "rejected_count":0,"matched_count":1,
               "matched":[{"fixture_id":fid,"kickoff_utc":utc_kickoff}]}
    values=[intake,shadow,browser]
    names=["MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
           "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json",
           "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json"]
    for name,value in zip(names,values):
        value.update(kw.get(name,{}))
        (folder/name).write_text(json.dumps(value),encoding="utf-8")

def test_selects_tomorrow_while_still_today_bogota(tmp_path):
    add(tmp_path,"2026-11-02","1","2026-11-02T05:15:00Z")
    result=choose(tmp_path,now=t("2026-11-02T04:10:00Z"))
    assert result["today_bogota"]=="2026-11-01"
    assert result["selected_date"]=="2026-11-02"
    assert result["selected_fixture_id"]=="1"
    assert result["seconds_until_kickoff"]==3900
    assert result["telegram_authorized"] is False

def test_selects_nearest_fixture_crossing_midnight(tmp_path):
    add(tmp_path,"2026-11-01","1","2026-11-02T04:50:00Z")
    add(tmp_path,"2026-11-02","2","2026-11-02T05:15:00Z")
    result=choose(tmp_path,now=t("2026-11-02T04:10:00Z"))
    assert result["selected_date"]=="2026-11-01"
    assert result["selected_fixture_id"]=="1"

def test_morning_without_any_fixtures_no_calls(tmp_path):
    add(tmp_path,"2026-11-02","1","2026-11-02T17:30:00Z")
    r=choose(tmp_path,now=t("2026-11-02T06:00:00Z"))
    assert r["selected_date"] is None
    assert r["status"]=="NO_CERTIFIED_PREMATCH_FIXTURES_IN_120M_WINDOW"

def test_kickoff_already_started_not_selected(tmp_path):
    add(tmp_path,"2026-11-02","1","2026-11-02T17:30:00Z")
    r=choose(tmp_path,now=t("2026-11-02T17:30:00Z"))
    assert r["selected_date"] is None

def test_nonmatching_browser_fixture_not_selected(tmp_path):
    add(tmp_path,"2026-11-02","1","2026-11-02T17:30:00Z")
    p=tmp_path/"2026-11-02"/"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json"
    b=json.loads(p.read_text())
    b["matched"][0]["fixture_id"]="NOT_THE_SAME"
    p.write_text(json.dumps(b))
    r=choose(tmp_path,now=t("2026-11-02T16:15:00Z"))
    assert r["selected_date"] is None

def test_source_date_mismatch_fails_closed(tmp_path):
    add(tmp_path,"2026-11-02","1","2026-11-02T17:30:00Z")
    p=tmp_path/"2026-11-02"/"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"
    s=json.loads(p.read_text());s["target_date_bogota"]="2026-11-03";p.write_text(json.dumps(s))
    r=choose(tmp_path,now=t("2026-11-02T16:15:00Z"))
    assert r["selected_date"] is None
    assert r["blocked_dates"]

def test_browser_rejections_block_whole_day(tmp_path):
    add(tmp_path,"2026-11-02","1","2026-11-02T17:30:00Z")
    p=tmp_path/"2026-11-02"/"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json"
    b=json.loads(p.read_text());b["rejected_count"]=1;p.write_text(json.dumps(b))
    r=choose(tmp_path,now=t("2026-11-02T16:15:00Z"))
    assert r["selected_date"] is None

def test_historic_signal_promotion_blocks_day(tmp_path):
    add(tmp_path,"2026-11-02","1","2026-11-02T17:30:00Z")
    p=tmp_path/"2026-11-02"/"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"
    s=json.loads(p.read_text());s["market_signal_authorized"]=True;p.write_text(json.dumps(s))
    r=choose(tmp_path,now=t("2026-11-02T16:15:00Z"))
    assert r["selected_date"] is None

def test_missing_artifacts_fails_without_crashing(tmp_path):
    r=choose(tmp_path,now=t("2026-11-02T16:15:00Z"))
    assert r["selected_date"] is None
    assert r["real_money"]=="BLOCKED"
    assert len(r["blocked_dates"])==2

def test_naive_clock_forbidden(tmp_path):
    try:
        choose(tmp_path,now=datetime(2026,11,2,16,15))
    except ValueError as exc:
        assert "NOW_REQUIRES_TIMEZONE" in str(exc)
    else:
        raise AssertionError("NAIVE_CLOCK_MUST_NOT_PASS")
