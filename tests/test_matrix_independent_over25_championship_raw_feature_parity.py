import json
from pathlib import Path

from tools.matrix_independent_over25_championship_raw_feature_parity import inspect


def _setup(tmp_path: Path):
    archive=tmp_path/"history.bin"
    archive.write_text(json.dumps({"response":[]}),encoding="utf-8")
    cycle=tmp_path/"cycle.json"
    cycle.write_text(json.dumps({"status":"PASS","finished_at_utc":"2026-10-24T09:39:53+00:00"}),encoding="utf-8")
    return archive,cycle


def test_no_provider_token_never_promotes_signal(tmp_path):
    archive,cycle=_setup(tmp_path)
    r=inspect("",archive=archive,cycle=cycle)
    assert r["status"]=="BLOCKED_MISSING_FREE_PROVIDER_KEY"
    assert r["network_calls"]==0
    assert r["reference_league_id"]==40
    assert r["source_league_id"]==2016
    assert r["original_calibrated_feature_equivalence_verified"] is False
    assert r["signal_generation_authorized"] is False
    assert r["real_money"]=="BLOCKED"


def test_archive_schema_invalid_fail_closed(tmp_path):
    archive,cycle=_setup(tmp_path)
    archive.write_text(json.dumps({"bad":[]}),encoding="utf-8")
    r=inspect("test-token",archive=archive,cycle=cycle)
    assert r["status"]=="BLOCKED_CHAMPIONSHIP_PARITY_PROBE_ERROR"
    assert r["network_calls"]==0


def test_non_pass_original_cycle_not_used(tmp_path):
    archive,cycle=_setup(tmp_path)
    cycle.write_text(json.dumps({"status":"FAIL","finished_at_utc":"2026-10-24T09:39:53+00:00"}),encoding="utf-8")
    r=inspect("test-token",archive=archive,cycle=cycle)
    assert r["status"]=="BLOCKED_CHAMPIONSHIP_PARITY_PROBE_ERROR"
    assert r["signal_generation_authorized"] is False


def test_unavailable_provider_is_reported_without_fabricating_parity(tmp_path):
    archive,cycle=_setup(tmp_path)
    def unavailable(*args,**kwargs):
        raise TimeoutError("provider unavailable")
    r=inspect("test-token",archive=archive,cycle=cycle,opener=unavailable)
    assert r["status"]=="BLOCKED_CHAMPIONSHIP_PARITY_PROBE_ERROR"
    assert r["network_calls"]==1
    assert r["original_calibrated_feature_equivalence_verified"] is False
    assert r["signal_generation_authorized"] is False
