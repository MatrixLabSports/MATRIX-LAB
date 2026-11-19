"""Continuity guard tests: real repo read-only plus tamper-only tmp copies.

The test never mutates the project or credits synthetic rows as observations.
"""
import json
import shutil
from pathlib import Path

from tools import matrix_hybrid_permanent_challenge_guard as guard

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (guard.CONTRACT, guard.PAIR, guard.MARKETS, guard.TENNIS, guard.OOS,
            guard.PAIR_WORKFLOW, guard.HISTORY_WORKFLOW, guard.EVALUATION_WORKFLOW,
            guard.BAYES_WORKFLOW, guard.THREE_WORKFLOW, guard.TEAM_V2_WORKFLOW,
            guard.FOUR_WORKFLOW, guard.DUAL_SOURCE_LINEAGE,
            guard.BAYES_V1_DIAGNOSTIC, *guard.PERMANENT_MODULES)


def copy_subset(tmp_path):
    for rel in REQUIRED:
        src = ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    manifest = json.loads((tmp_path / guard.PAIR).read_bytes())
    for row in manifest["prelabel_research_pairs"]:
        for key in ("original_freeze_path", "poisson_freeze_path"):
            rel = Path(row[key])
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, target)
    return tmp_path


def test_real_source_contract_and_four_lanes_remain_present():
    r = guard.inspect(ROOT)
    assert r["technical_integrity_pass"], r["integrity_failures"]
    assert r["status"] == "CONTROLS_VALID_RESEARCH_STILL_BLOCKED"
    assert r["market_scope"]["total"] == 42
    assert r["market_scope"]["football"] == 30
    assert r["market_scope"]["tennis"] == 12
    assert set(r["all_four_lanes"]) == set(guard.REQUIRED_LANES)
    assert r["all_four_lanes"]["FOOTBALL_OVER25"]["research_frozen_pairs"] >= 37
    assert r["official_hybrid_p_matrix_comparison_certified"] is False
    assert r["challenge_completed"] is False
    assert r["real_money"] == "BLOCKED"
    assert r["telegram_signal_authorized"] is False


def test_modified_immutable_poisson_freeze_fails_closed(tmp_path):
    root = copy_subset(tmp_path)
    j = json.loads((root / guard.PAIR).read_bytes())
    frozen = root / j["prelabel_research_pairs"][0]["poisson_freeze_path"]
    frozen.write_bytes(frozen.read_bytes() + b" ")
    r = guard.inspect(root)
    assert r["technical_integrity_pass"] is False
    assert any("PHYSICAL_FREEZE_SHA_MISMATCH_poisson" in x for x in r["integrity_failures"])


def test_market_scope_change_fails_closed(tmp_path):
    root = copy_subset(tmp_path)
    p = root / guard.MARKETS
    j = json.loads(p.read_bytes())
    j["total_lanes"] = 41
    p.write_text(json.dumps(j))
    r = guard.inspect(root)
    assert "MARKET_SCOPE_OR_SCHEMA_NOT_42" in r["integrity_failures"]


def test_no_hybrid_contract_fails_closed(tmp_path):
    root = copy_subset(tmp_path)
    (root / guard.CONTRACT).unlink()
    r = guard.inspect(root)
    assert "MISSING_HYBRID_PERMANENT_CONTRACT" in r["integrity_failures"]


def test_loss_of_daily_schedule_fails_closed(tmp_path):
    root = copy_subset(tmp_path)
    p = root / guard.PAIR_WORKFLOW
    p.write_text(p.read_text().replace("schedule:", "manual:"))
    r = guard.inspect(root)
    assert "SCHEDULED_WORKFLOW_INCOMPLETE:hybrid_pairs" in r["integrity_failures"]


def test_unapproved_model_promotion_fails_closed(tmp_path):
    root = copy_subset(tmp_path)
    p = root / guard.PAIR
    j = json.loads(p.read_bytes())
    j["production_p_matrix_authorized"] = True
    p.write_text(json.dumps(j))
    r = guard.inspect(root)
    assert "UNAUTHORIZED_HYBRID_PROMOTION:production_p_matrix_authorized" in r["integrity_failures"]


def test_missing_bayesian_schedule_fails_closed(tmp_path):
    root = copy_subset(tmp_path)
    (root / guard.BAYES_WORKFLOW).unlink()
    r = guard.inspect(root)
    assert "MISSING_SCHEDULED_WORKFLOW:bayesian_prospective" in r["integrity_failures"]


def test_missing_original_hybrid_lab_fails_closed(tmp_path):
    root = copy_subset(tmp_path)
    (root / guard.PERMANENT_MODULES[0]).unlink()
    r = guard.inspect(root)
    assert any("MISSING_PERMANENT_HYBRID_MODEL" in reason
               for reason in r["integrity_failures"])


def test_all_physical_continuity_sources_copy_to_isolated_test_root(tmp_path):
    root = copy_subset(tmp_path)
    r = guard.inspect(root)
    assert r["technical_integrity_pass"], r["integrity_failures"]
    assert set(r["automated_workflows_present"]) == {
        "hybrid_pairs", "free_D2", "independent_OOS",
        "bayesian_prospective", "three_model_prospective_oos",
        "team_aware_bayesian_v2", "four_model_prospective_oos",
    }
    assert r["hybrid_three_model_oos"]["state"] in (
        "PENDING_FIRST_VERIFIED_CYCLE",
        "THREE_RESEARCH_MODELS_PROSPECTIVE_EVALUATION_NO_PROMOTION")
    assert r["challenge_completed"] is False


def test_missing_three_model_evaluation_schedule_is_caught(tmp_path):
    root = copy_subset(tmp_path)
    (root / guard.THREE_WORKFLOW).unlink()
    r = guard.inspect(root)
    assert "MISSING_SCHEDULED_WORKFLOW:three_model_prospective_oos" in r["integrity_failures"]


def test_missing_team_venue_bayesian_v2_model_is_caught(tmp_path):
    root = copy_subset(tmp_path)
    (root / guard.PERMANENT_MODULES[-1]).unlink()
    r = guard.inspect(root)
    assert "MISSING_PERMANENT_HYBRID_MODEL:" + (
        guard.PERMANENT_MODULES[-1].as_posix()) in r["integrity_failures"]


def test_missing_four_model_prospective_schedule_fails_closed(tmp_path):
    root=copy_subset(tmp_path)
    (root / guard.FOUR_WORKFLOW).unlink()
    state=guard.inspect(root)
    assert "MISSING_SCHEDULED_WORKFLOW:four_model_prospective_oos" in state["integrity_failures"]


def test_modified_dual_capture_attestation_fails_closed(tmp_path):
    root=copy_subset(tmp_path)
    p=root / guard.DUAL_SOURCE_LINEAGE
    j=json.loads(p.read_bytes())
    j["lineage_matched_fixture_count"]=0
    p.write_text(json.dumps(j),encoding="utf-8")
    state=guard.inspect(root)
    assert "INVALID_PRIMARY_VS_SECONDARY_FORMULA_SHA_LINEAGE" in state["integrity_failures"]
