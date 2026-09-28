from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_prospective_market_freeze import build_freeze
from tools.api_football_prospective_market_settlement import settle
from tools.api_football_prediction_store import load_chunked_json


def test_prospective_freeze_is_future_unseen_and_holdout_safe():
    d=build_freeze(Path("."),datetime.now(timezone.utc))
    assert d["frozen_event_count"]>0
    assert d["protections"]["future_only"] is True
    assert d["protections"]["unseen_events_only"] is True
    assert d["protections"]["original_357_holdout_excluded"] is True
    assert d["protections"]["outcomes_read_at_freeze"] is False
    assert d["protections"]["missing_feature_imputation"] is False
    assert d["protections"]["p_matrix_generated"] is False
    assert d["protections"]["real_money"]=="BLOCKED"
    forbidden=set(__import__("json").loads(Path("evidence/api_football/btts_challenger_v2/exclusion_registry.json").read_text())["forbidden_fixture_ids"])
    seen=set(str(r["fixture_id"]) for r in load_chunked_json(Path("evidence/api_football/model_validation/retrospective_predictions_manifest.json"))["rows"])
    for row in d["rows"]:
        assert str(row["fixture_id"]) not in forbidden
        assert str(row["fixture_id"]) not in seen
        assert row["outcome"] is None
        assert row["settlement_status"]=="PENDING_FINAL"
        assert datetime.fromisoformat(row["freeze_at_utc"]) < datetime.fromisoformat(row["kickoff_utc"])


def test_settlement_never_marks_nonfinal_as_final():
    root=Path(".")
    d=settle(root)
    assert d["settlement_summary"]["settlement_final_only"] is True
    assert d["settlement_summary"]["nonfinal_outcomes_read"] is False
    for row in d["rows"]:
        if row["settlement_status"]!="FINAL":
            assert row["outcome"] is None
