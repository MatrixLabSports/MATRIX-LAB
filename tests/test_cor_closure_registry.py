import json
from pathlib import Path

ROOT=Path(".")
REGISTRY=ROOT/"evidence/audit/MATRIX_COR_CLOSURE_REGISTRY.json"

def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_all_nine_resolved_cors_have_physical_closure_paths():
    r=_load(REGISTRY)
    assert r["resolved_count"]==9
    assert set(r["resolved"])=={"COR01","COR04","COR05","COR06","COR07","COR08","COR09","COR10","COR12"}
    assert set(r["in_progress"])=={"COR02","COR03","COR11"}
    for cor in r["resolved"]:
        p=ROOT/r["entries"][cor]["path"]
        assert p.exists(), (cor,p)
        d=_load(p)
        assert d["status"]=="RESOLVED"

def test_all_manifest_evidence_paths_exist():
    r=_load(REGISTRY)
    for cor in ("COR01","COR04","COR05","COR07","COR08","COR09","COR12"):
        d=_load(ROOT/r["entries"][cor]["path"])
        for src in d["evidence"]:
            assert (ROOT/src["path"]).exists(), (cor,src["path"])

def test_scope_caveats_cannot_regress():
    r=_load(REGISTRY)
    assert r["invariants"]["external_audit_closed"] is False
    assert r["invariants"]["real_money"]=="BLOCKED"
    assert r["invariants"]["cor07_does_not_imply_engine_executable"] is True
    assert r["invariants"]["cor08_is_historical_acceptance"] is True
    assert r["invariants"]["cor09_does_not_satisfy_three_cycle_go_nogo"] is True
    assert r["invariants"]["cor12_does_not_authorize_real_money"] is True
    c7=_load(ROOT/r["entries"]["COR07"]["path"])
    assert c7["engine_executable_count"]==0
    c9=_load(ROOT/r["entries"]["COR09"]["path"])
    assert c9["go_nogo_three_cycle_yield_satisfied"] is False
    c12=_load(ROOT/r["entries"]["COR12"]["path"])
    assert c12["real_money_authorized"] is False

def test_current_cor04_integrity_remains_clean():
    d=_load(ROOT/"evidence/cor0203/runtime/MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json")
    assert d["result"]=="PASS"
    assert d["failed_observations"]==0
    assert d["metrics_opened"] is False
    assert d["outcomes_read"]==0
    assert d["silent_imputation_detected"] is False

def test_cor10_is_real_future_shadow_evidence_not_vacuous():
    d=_load(ROOT/"evidence/cor10/MATRIX_COR10_ADJUDICATION.json")
    assert d["pass"] is True
    assert d["execution_count"]>=1
    assert d["future_execution_count"]>=1
    assert d["future_execution_rate"]==1.0
    assert d["real_money"]=="BLOCKED"
