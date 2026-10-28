import json
from pathlib import Path
from tools.matrix_quote_pipeline_certification import build

def test_certification_is_fail_closed():
    out=build()
    assert out["criteria"]["post_fix_infrastructure_loss_count_must_equal"]==0
    assert out["automatic_wagering"] is False
    assert out["real_money"]=="BLOCKED"
    if out["observed"]["post_fix_infrastructure_loss_count"]>0:
        assert out["status"]=="NO_GO_CERTIFICATION_FAILED"
        assert "INFRASTRUCTURE_CANDIDATES_LOST_BEFORE_TELEGRAM" in out["failures"]

def test_queue_sync_is_mandatory():
    out=build()
    if not out["observed"]["recovery_queue_synced"]:
        assert "RECOVERY_QUEUE_NOT_SYNCHRONIZED_WITH_LATEST_AUDIT" in out["failures"]
