"""Empty Opera inbox must not be reported as successful ingestion."""
import json
from tools import physical_team_total_browser_capture as bridge

def test_empty_inbox_is_no_input(monkeypatch, tmp_path, capsys):
    import sys
    inbox=tmp_path/"inbox"
    audit=tmp_path/"audit.json"
    monkeypatch.setattr(sys,"argv",["capture","--inbox",str(inbox),"--out-root",str(tmp_path/"out"),"--audit",str(audit)])
    bridge.main()
    payload=json.loads(audit.read_text(encoding="utf-8"))
    assert payload["status"]=="NO_INPUT"
    assert payload["input_count"]==0
    assert payload["accepted_count"]==0
    assert json.loads(capsys.readouterr().out)["status"]=="NO_INPUT"
