"""Read-only quote-window scopes; all odds provider calls are separate."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest

from tools.matrix_championship_quote_window_scope import scope
from tools.matrix_championship_prospective_pit_attestation import report

ROOT=Path(__file__).resolve().parents[1]/"evidence"/"football_world_inventory"/"2026-11-03"
FILES=[
    "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
    "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json",
    "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
    "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",
]

def originals():
    """Replay actual archived provider rows at their original capture timestamp.

    Never reuse a newer intake with an older independent attestation.
    """
    intake, shadow, sofa, flash = [
        json.loads((ROOT/path).read_text(encoding="utf-8")) for path in FILES
    ]
    score_completed=datetime.fromisoformat(shadow["completed_at_utc"].replace("Z","+00:00"))
    attestation=report(intake,sofa,flash,shadow,
                       now=score_completed)
    assert attestation["prospective_research_history_certified_count"]==6
    return intake,shadow,attestation,sofa,flash

def test_real_archived_prospective_pre_match_window_has_six_only_research_targets():
    source,shadow,att,sofa,flash=originals()
    x,y,gate=scope(source,shadow,att,sofa,flash,
                   now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))
    assert gate["research_only_eligible_count"]==6
    assert set(gate["research_only_ids"])=={
        "561917","561918","561921","561922","561924","561928"}
    assert x["fixture_count"]==6
    assert y["scored_count"]==6
    assert x["signal_generation_authorized"] is False
    assert y["market_signal_authorized"] is False
    assert gate["production_probability_authorized"] is False
    assert gate["telegram_signal_authorized"] is False
    assert gate["real_money"]=="BLOCKED"
    assert all("p_matrix" not in row for row in y["scored"])


def test_outside_two_hour_window_is_zero_and_never_price_eligible():
    d=originals()
    # This is an archived evidence replay, and the actual provider capture
    # timestamp changes after each successful independent workflow. A hard-
    # coded 14:00 UTC can precede that real capture and falsely fail STALE.
    captured=datetime.fromisoformat(d[0]["generated_at_utc"].replace("Z","+00:00"))
    observed=datetime.fromisoformat(d[2]["observed_at_utc"].replace("Z","+00:00"))
    clock=max(captured,observed)+__import__("datetime").timedelta(seconds=30)
    assert all((datetime.fromisoformat(x["kickoff_utc"].replace("Z","+00:00"))-clock).total_seconds()>7200
               for x in d[2]["rows"] if x["status"]=="PASS_PROSPECTIVE_RESEARCH_HISTORY_ONLY")
    x,y,gate=scope(*d,now=clock)
    assert gate["research_only_eligible_count"]==0
    assert x["fixtures"]==[]
    assert y["scored"]==[]


def test_started_fixture_never_eligible():
    d=originals()
    _,_,gate=scope(*d,now=datetime(2026,11,3,21,0,tzinfo=timezone.utc))
    assert gate["research_only_eligible_count"]==0


def test_incorrect_browser_kickoff_blocks_target():
    source,shadow,att,sofa,flash=originals()
    flash=deepcopy(flash)
    match=next(r for r in flash["matched"] if r["source_fixture_id"]=="561918")
    match["kickoff_utc"]="2026-11-03T20:00:00+00:00"
    # Changing a verified browser kickoff invalidates its four-source hash.
    # We must block the ENTIRE mixed snapshot, not quietly score five others.
    with pytest.raises(ValueError,match="EXACT_SOURCE_SNAPSHOT"):
        scope(source,shadow,att,sofa,flash,
              now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))


def test_source_gov_change_fails_closed():
    source,shadow,att,sofa,flash=originals()
    source=deepcopy(source);source["real_money"]="ENABLED"
    with pytest.raises(ValueError,match="GOVERNANCE"):
        scope(source,shadow,att,sofa,flash,
              now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))


def test_stale_source_fails_closed():
    source,shadow,att,sofa,flash=originals()
    source=deepcopy(source);source["generated_at_utc"]="2026-10-29T05:00:00+00:00"
    # An altered timestamp is blocked first by the stronger hash contract.
    with pytest.raises(ValueError,match="EXACT_SOURCE_SNAPSHOT"):
        scope(source,shadow,att,sofa,flash,
              now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))


def test_attestation_from_a_different_source_capture_is_rejected():
    intake,shadow,att,sofa,flash=originals()
    intake=deepcopy(intake)
    intake["generated_at_utc"]="2026-11-03T10:48:00+00:00"
    with pytest.raises(ValueError,match="EXACT_SOURCE_SNAPSHOT"):
        scope(intake,shadow,att,sofa,flash,
              now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))

def test_single_history_probability_mutation_without_new_attestation_blocks():
    intake,shadow,att,sofa,flash=originals()
    shadow=deepcopy(shadow)
    shadow["scored"][0]["p_over25_research"]=0.99
    with pytest.raises(ValueError,match="EXACT_SOURCE_SNAPSHOT"):
        scope(intake,shadow,att,sofa,flash,
              now=datetime(2026,11,3,18,30,tzinfo=timezone.utc))


def test_main_selects_older_exact_snapshot_over_newer_mismatched_one(tmp_path,monkeypatch):
    """Physical candidate inputs can update independently during a day."""
    from datetime import datetime,timezone
    import sys
    from tools.matrix_championship_quote_window_scope import main
    intake,shadow,att,sofa,flash=originals()
    folder=tmp_path/"evidence"/"football_world_inventory"/"2026-11-03"
    folder.mkdir(parents=True)
    filenames={
        "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json":intake,
        "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json":shadow,
        "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json":sofa,
        "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json":flash,
    }
    for name,doc in filenames.items():
        (folder/name).write_text(json.dumps(doc),encoding="utf-8")
    good=folder/"MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_RUN_111.json"
    good.write_text(json.dumps(att),encoding="utf-8")
    bad=deepcopy(att)
    bad["source_shadow_sha256"]="0"*64
    bad["observed_at_utc"]=datetime.now(timezone.utc).isoformat()
    (folder/"MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_RUN_222.json").write_text(
        json.dumps(bad),encoding="utf-8")
    status=tmp_path/"scope.json"
    monkeypatch.delenv("GITHUB_OUTPUT",raising=False)
    monkeypatch.setattr(sys,"argv",["quote_scope","--date","2026-11-03",
        "--root",str(tmp_path),"--outdir",str(tmp_path/"output"),
        "--status-out",str(status)])
    main()
    chosen=json.loads(status.read_text(encoding="utf-8"))
    assert chosen["source_attestation_file"]==good.name
    assert chosen["status"] in (
        "NO_VERIFIED_PREMATCH_SCOPE","PREMATCH_RESEARCH_QUOTE_SCOPE_AVAILABLE")
    assert chosen["telegram_signal_authorized"] is False


def test_main_blocks_all_mismatched_attestations_without_querying_odds(tmp_path,monkeypatch):
    import sys
    from tools.matrix_championship_quote_window_scope import main
    intake,shadow,att,sofa,flash=originals()
    folder=tmp_path/"evidence"/"football_world_inventory"/"2026-11-03"
    folder.mkdir(parents=True)
    for name,doc in {
        "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json":intake,
        "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json":shadow,
        "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json":sofa,
        "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json":flash,
    }.items():
        (folder/name).write_text(json.dumps(doc),encoding="utf-8")
    att=deepcopy(att)
    att["source_shadow_sha256"]="0"*64
    (folder/"MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_RUN_333.json").write_text(
        json.dumps(att),encoding="utf-8")
    status=tmp_path/"scope.json"
    monkeypatch.delenv("GITHUB_OUTPUT",raising=False)
    monkeypatch.setattr(sys,"argv",["quote_scope","--date","2026-11-03",
        "--root",str(tmp_path),"--outdir",str(tmp_path/"output"),
        "--status-out",str(status)])
    main()
    result=json.loads(status.read_text(encoding="utf-8"))
    assert result["status"]=="BLOCKED_NO_EXACT_SOURCE_ATTESTATION"
    assert result["research_only_eligible_count"]==0
    assert result["telegram_signal_authorized"] is False
    assert not (tmp_path/"output"/"intake.json").exists()


def test_main_uses_immutable_atomic_snapshot_even_if_current_daily_intake_drifted(tmp_path,monkeypatch):
    import sys
    from datetime import timedelta
    import tools.matrix_championship_quote_window_scope as mod
    from tools.matrix_championship_atomic_pit_cycle import pack
    intake,shadow,att,sofa,flash=originals()
    folder=tmp_path/"evidence"/"football_world_inventory"/"2026-11-03"
    folder.mkdir(parents=True)
    docs={"intake":intake,"shadow":shadow,"sofa":sofa,"flash":flash,
          "attestation":att}
    bundle=pack(docs,run_id="777")
    name="MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_777.json"
    (folder/name).write_text(json.dumps(bundle),encoding="utf-8")
    # A different independent pipeline has just overwritten ONLY the daily
    # intake. Mixed daily files are rejected; bundle remains unchanged.
    daily=deepcopy(intake)
    daily["fixtures"][0]["home"]="Unverified replacement"
    names={
        "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json":daily,
        "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json":shadow,
        "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json":sofa,
        "MATRIX_FLASH_FOOTBALL_CROSSCHECK.json":flash,
    }
    for filename,data in names.items():
        (folder/filename).write_text(json.dumps(data),encoding="utf-8")
    at=datetime.fromisoformat(bundle["attested_at_utc"])
    class ReplayClock(datetime):
        @classmethod
        def now(cls,tz=None):
            t=at+timedelta(minutes=2)
            return t.astimezone(tz) if tz else t.replace(tzinfo=None)
    monkeypatch.setattr(mod,"datetime",ReplayClock)
    monkeypatch.delenv("GITHUB_OUTPUT",raising=False)
    status=tmp_path/"status.json"
    monkeypatch.setattr(sys,"argv",["scope","--date","2026-11-03",
        "--root",str(tmp_path),"--outdir",str(tmp_path/"scope"),
        "--status-out",str(status)])
    mod.main()
    result=json.loads(status.read_text(encoding="utf-8"))
    assert result["source_attestation_file"]==name
    assert result["telegram_signal_authorized"] is False
    assert result["production_probability_authorized"] is False
    output=json.loads((tmp_path/"scope"/"intake.json").read_text(encoding="utf-8"))
    assert output["research_quote_scope_only"] is True
    assert all(row["home"]!="Unverified replacement" for row in output["fixtures"])

def test_atomic_snapshot_rejects_laundered_single_input(tmp_path):
    from tools.matrix_championship_atomic_pit_cycle import pack
    from tools.matrix_championship_quote_window_scope import atomic_cycles
    from datetime import timedelta
    intake,shadow,att,sofa,flash=originals()
    b=pack({"intake":intake,"shadow":shadow,"sofa":sofa,"flash":flash,
            "attestation":att},run_id="111")
    b["documents"]["shadow"]["scored"][0]["p_over25_research"]=0.999
    folder=tmp_path/"evidence"/"football_world_inventory"/"2026-11-03"
    folder.mkdir(parents=True)
    (folder/"MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_111.json").write_text(
        json.dumps(b),encoding="utf-8")
    now=datetime.fromisoformat(b["attested_at_utc"])+timedelta(minutes=5)
    assert atomic_cycles(folder,"2026-11-03",now=now)==[]
