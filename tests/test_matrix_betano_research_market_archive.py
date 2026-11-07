"""Archive real, research-only Betano markets without touching execution."""
import json
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_selfhosted_browser_quote_collector import persist_research_market

NOW=datetime(2026,11,3,23,37,26,tzinfo=timezone.utc)

def rec():
    return {
      "fixture_id":"FOOTBALL_DATA_ORG:575387",
      "kickoff":"2026-11-04T17:45:00+00:00",
      "p_matrix":None,"research_only":True,
      "execution_quote_emitted":False,"telegram_signal_authorized":False,
      "exact_quote":{
        "event_id":"91590438","event_url":"/cuotas-de-partido/fenerbahce-sk-liverpool-fc/91590438/",
        "market_name":"Goles totales Más/Menos",
        "selection_name":"Más de 2.5","handicap":2.5,"price":1.4}
    }

def test_archives_a_single_content_addressed_research_price(tmp_path:Path):
    path=persist_research_market(rec(),NOW,tmp_path)
    assert path is not None
    evidence=json.loads((tmp_path/path).read_text(encoding="utf-8"))
    assert evidence["decimal_price"]==1.4
    assert evidence["event_id"]=="91590438"
    assert evidence["research_only"] is True
    assert evidence["production_probability_authorized"] is False
    assert evidence["execution_quote_emitted"] is False
    assert evidence["telegram_signal_authorized"] is False
    assert evidence["real_money"]=="BLOCKED"
    assert persist_research_market(rec(),NOW,tmp_path)==path
    assert len(list((tmp_path/"evidence").rglob("MATRIX_BETANO_RESEARCH_MARKET_*.json")))==1

def test_cannot_archive_as_official_quote(tmp_path):
    x=rec();x["research_only"]=False
    assert persist_research_market(x,NOW,tmp_path) is None
    x=rec();x["p_matrix"]=.65
    assert persist_research_market(x,NOW,tmp_path) is None
    x=rec();x["execution_quote_emitted"]=True
    assert persist_research_market(x,NOW,tmp_path) is None
    x=rec();x["telegram_signal_authorized"]=True
    assert persist_research_market(x,NOW,tmp_path) is None
    x=rec();x["exact_quote"]["selection_name"]="Menos de 2.5"
    assert persist_research_market(x,NOW,tmp_path) is None
    assert not (tmp_path/"evidence").exists()

def test_cannot_archive_after_kickoff(tmp_path):
    assert persist_research_market(rec(),datetime(2026,11,4,18,tzinfo=timezone.utc),tmp_path) is None
