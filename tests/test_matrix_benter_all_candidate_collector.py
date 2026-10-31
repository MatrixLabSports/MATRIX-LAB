from pathlib import Path
import json
from tools.matrix_benter_all_candidate_collector import build,extract_books

def test_extract_books_devigs_exact_over_under_pair():
    payload={"response":[{"update":"2026-10-16T12:00:00+00:00","bookmakers":[
        {"id":1,"name":"A","bets":[{"id":5,"name":"Goals Over/Under","values":[{"value":"Over 2.5","odd":"2.00"},{"value":"Under 2.5","odd":"1.80"}]}]},
        {"id":2,"name":"B","bets":[{"id":5,"name":"Goals Over/Under","values":[{"value":"Over 2.5","odd":"1.90"},{"value":"Under 2.5","odd":"1.95"}]}]}
    ]}]}
    books=extract_books(payload)
    assert len(books)==2
    for b in books:
        assert abs(b["devig_over_probability"]+b["devig_under_probability"]-1.0)<1e-12
        assert b["overround"]>1.0

def test_build_uses_all_scored_candidates_not_only_signals(tmp_path:Path):
    raw=tmp_path/"raw"; raw.mkdir()
    payload={"response":[{"update":"2026-10-16T12:00:00+00:00","bookmakers":[
        {"id":1,"name":"A","bets":[{"id":5,"name":"Goals Over/Under","values":[{"value":"Over 2.5","odd":"2.00"},{"value":"Under 2.5","odd":"1.80"}]}]},
        {"id":2,"name":"B","bets":[{"id":5,"name":"Goals Over/Under","values":[{"value":"Over 2.5","odd":"1.90"},{"value":"Under 2.5","odd":"1.95"}]}]}
    ]}]}
    for fid in ("1","2"):
        (raw/f"fixture_{fid}.bin").write_text(json.dumps(payload),encoding="utf-8")
    report={"all_rows":[
        {"fixture_id":"1","match":"A vs B","kickoff_utc":"2026-10-16T18:00:00+00:00","p_over_2_5":0.62,"decision":"BET_SHADOW"},
        {"fixture_id":"2","match":"C vs D","kickoff_utc":"2026-10-16T19:00:00+00:00","p_over_2_5":0.48,"decision":"BLOCKED"},
        {"fixture_id":"3","p_over_2_5":None,"decision":"BLOCKED"},
    ]}
    out=build(report,raw)
    assert out["row_count"]==2
    assert out["devigged_consensus_count"]==2
    assert out["governance"]["all_scored_candidates_not_signal_selected_only"] is True
    assert all(r["outcome_over25"] is None for r in out["rows"])
    assert out["governance"]["market_probability_fused_into_production"] is False
    assert out["governance"]["real_money"]=="BLOCKED"
