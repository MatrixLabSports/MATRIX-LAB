import json
from pathlib import Path

from tools.cor0203_holdout_integrity_audit import audit_holdout

ROOT = Path(__file__).resolve().parents[1]


def test_current_holdout_chain_excludes_r706_and_has_no_silent_fallbacks():
    report = audit_holdout(
        runtime_dir=ROOT / "evidence/cor0203/runtime",
        holdout_dir=ROOT / "evidence/cor0203/holdout",
        state_b64=ROOT / "evidence/cor0203/runtime/MATRIX_COR0203_PRE2026_STATE_R706.json.gz.b64",
        bundle_path=ROOT / "evidence/cor0203/runtime/MATRIX_COR0203_ELO_GLICKO_PROSPECTIVE_BUNDLE_R706.json",
        annual_2026=ROOT / "evidence/cor0203/preholdout/2026_challenger_live_snapshot.csv",
        binding_path=ROOT / "evidence/cor0203/runtime/MATRIX_COR0203_MODEL_BINDING_R707.json",
    )
    assert report["result"] == "PASS"
    assert report["admissible_batch_revisions"] == [707, 708, 713, 718, 722]
    assert report["admissible_observations"] == 10
    assert report["audited_observations"] == 10
    assert report["passed_observations"] == 10
    assert report["failed_observations"] == 0
    assert report["outcomes_read"] == 0
    assert report["metrics_opened"] is False
    assert report["median_or_neutral_fallback_admissible"] is False
    assert any(row["revision"] == 706 for row in report["quarantined_batches"])
