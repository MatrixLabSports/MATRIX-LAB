import hashlib
import json
from pathlib import Path

from tools.physical_team_total_browser_capture import _validate, main


def _row():
    text="Betano physical accessibility snapshot: Manchester United team total over 1.5 @ 1.80"
    return {
        "schema":"MATRIX_BROWSER_TEAM_TOTAL_CAPTURE_V1",
        "captured_at_utc":"2026-10-25T07:40:00+00:00",
        "fixture_id":"999",
        "kickoff_utc":"2026-10-25T08:00:00+00:00",
        "match":"Manchester United vs Arsenal",
        "league":"Premier League",
        "market_lane":"TEAM_TOTAL_GOALS_HOME",
        "team_name":"Manchester United",
        "selection_side":"over",
        "line":1.5,
        "house":"Betano",
        "decimal_odds":1.80,
        "source_url":"https://www.betano.co/cuotas-de-partido/example/",
        "source_text_sha256":hashlib.sha256(text.encode()).hexdigest(),
    }


def test_validate_accepts_exact_physical_capture():
    artifact,reason=_validate(_row())
    assert reason=="PASS"
    assert artifact is not None
    assert artifact["schema"]=="MATRIX_PHYSICAL_BOOK_QUOTE_V1"
    assert artifact["market_key"]=="TEAM_TOTAL_GOALS_HOME"
    assert artifact["team_name"]=="Manchester United"
    assert artifact["selection_side"]=="over"
    assert artifact["line"]==1.5
    assert artifact["house_key"]=="betano"
    assert artifact["decimal_odds"]==1.80
    assert artifact["automatic_wagering"] is False
    assert artifact["real_money"]=="BLOCKED"


def test_validate_rejects_post_kickoff_capture():
    row=_row()
    row["captured_at_utc"]="2026-10-25T08:01:00+00:00"
    artifact,reason=_validate(row)
    assert artifact is None
    assert reason=="POST_KICKOFF"


def test_validate_rejects_missing_proof_hash():
    row=_row(); row["source_text_sha256"]=""
    artifact,reason=_validate(row)
    assert artifact is None
    assert reason=="SOURCE_HASH"


def test_bridge_writes_canonical_artifact_and_audit(tmp_path,monkeypatch):
    inbox=tmp_path/"inbox"; out=tmp_path/"out"; audit=tmp_path/"audit.json"
    inbox.mkdir()
    (inbox/"capture.json").write_text(json.dumps(_row()),encoding="utf-8")
    monkeypatch.setattr("sys.argv",["prog","--inbox",str(inbox),"--out-root",str(out),"--audit",str(audit)])
    main()
    payload=json.loads(audit.read_text(encoding="utf-8"))
    assert payload["status"]=="PASS"
    assert payload["accepted_count"]==1
    files=list(out.rglob("MATRIX_TEAM_TOTAL_*_QUOTE_*_UTC.json"))
    assert len(files)==1
    artifact=json.loads(files[0].read_text(encoding="utf-8"))
    assert artifact["schema"]=="MATRIX_PHYSICAL_BOOK_QUOTE_V1"
    assert artifact["source"]=="Opera Browser Connector physical accessibility tree"
