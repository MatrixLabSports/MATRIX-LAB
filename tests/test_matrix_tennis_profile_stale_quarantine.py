"""Stale tennis profile evidence must not block fresh browser captures or enter ratings."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.matrix_tennis_profile_stale_quarantine import run,SCHEMA

DAY="2026-11-22"
def setup(tmp_path):
    root=tmp_path/"evidence/tennis_calendar_physical"/DAY
    root.mkdir(parents=True)
    (root/"MATRIX_TENNIS_FREE_VISIBLE_PROFILE_BIRTHDATES_RESEARCH.json").write_text('{"test":true}')
    (root/"sofascore_verified_match_details.json").write_text('{"real_source":"fake_test_only"}')
    return tmp_path
def test_explicit_stale_pre_cut_only_quarantined_never_admitted(tmp_path):
    root=setup(tmp_path)
    def failed(*args,**kwargs):
        assert "--date" in args[0] and DAY in args[0]
        return SimpleNamespace(returncode=1,stdout="",stderr="ValueError: PROFILE_AUDIT_PRECUT_HISTORY_NOT_PRECUT")
    d=run(DAY,root=root,runner=failed)
    assert d["schema"]==SCHEMA and d["quarantined"] is True
    assert d["status"]=="STALE_PROFILE_PRE_CUT_EVIDENCE_QUARANTINED_NO_MODEL_ADMISSION"
    assert d["hard_holdout_admitted"]==d["clay_holdout_admitted"]==0
    assert len(d["source_files_sha256"])==2
    assert d["telegram_signal_authorized"] is False
def test_non_stale_failure_not_swallowed(tmp_path):
    root=setup(tmp_path)
    with pytest.raises(RuntimeError,match="UNEXPECTED_TENNIS_PROFILE_AUDIT_FAILURE"):
        run(DAY,root=root,runner=lambda *a,**k:SimpleNamespace(returncode=1,stdout="",stderr="HTTP_429"))
def test_good_source_not_quarantined_or_promoted(tmp_path):
    root=setup(tmp_path)
    d=run(DAY,root=root,runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout="done",stderr=""))
    assert d["quarantined"] is False
    assert d["status"]=="CURRENT_PROFILE_PIT_BINDING_COMPLETED"
    assert d["model_admission_authorized"] is False
def test_missing_profile_is_not_guessed(tmp_path):
    d=run(DAY,root=tmp_path,runner=lambda *a,**k:pytest.fail("MUST_NOT_CALL_SUBPROCESS"))
    assert d["status"]=="MISSING_PROFILE_OR_DETAIL_SOURCE"
    assert d["hard_holdout_admitted"]==0
