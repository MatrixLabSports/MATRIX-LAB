from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/cor0203-batch-freeze.yml"
BATCH = ROOT / "evidence/cor0203/holdout/MATRIX_COR0203_HOLDOUT_BATCH_R718.json"
HISTORY = ROOT / "evidence/cor0203/runtime/MATRIX_COR0203_HISTORY_GATE_R718.json"
PREFEATURE = ROOT / "evidence/cor0203/runtime/MATRIX_COR0203_PREFEATURE_REGISTRY_R718.json"


def test_r718_freeze_timestamp_is_exported_for_same_step_python():
    text = WORKFLOW.read_text(encoding="utf-8")
    freeze_assign = 'FREEZE_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"'
    export = "export FREEZE_AT"
    python_env_read = "os.environ['FREEZE_AT']"
    assert freeze_assign in text
    assert export in text
    assert python_env_read in text
    assert text.index(freeze_assign) < text.index(export) < text.index(python_env_read)


def test_r718_is_observation_9_and_stays_sealed():
    x = json.loads(BATCH.read_text(encoding="utf-8"))
    assert x["starting_observation_count"] == 8
    assert x["added_observations"] == 1
    assert x["ending_observation_count"] == 9
    assert x["window1_count"] == 9
    assert x["metrics"] == "SEALED_UNTIL_600"
    assert x["outcomes_read"] == 0
    assert x["real_money"] == "BLOCKED"
    assert len(x["observations"]) == 1
    o = x["observations"][0]
    assert o["observation_index"] == 9
    assert o["event_id"] == "COR0203-R718-STT-MAYOT-CASSONE"
    assert o["outcome"] is None
    assert o["metrics_opened"] is False
    assert o["freeze_at_utc"] < o["event_start_utc"]
    assert o["elo"]["model_id"] == "R218_ELO_BOTH"
    assert o["glicko"]["model_id"] == "R223_BATCH_GLICKO_RATING_BOTH"


def test_r718_history_gate_and_prefeature_ordering():
    h = json.loads(HISTORY.read_text(encoding="utf-8"))
    p = json.loads(PREFEATURE.read_text(encoding="utf-8"))
    assert h["result"] == "PASS"
    assert h["same_period_results_used"] is False
    assert h["silent_imputation"] is False
    assert h["players"]["Harold Mayot"]["n_history"] == 184
    assert h["players"]["Murphy Cassone"]["n_history"] == 89
    assert p["created_before_feature_acquisition"] is True
    assert p["starting_observation_count"] == 8
    assert p["events"][0]["features_loaded"] is False
    assert p["events"][0]["outcome"] is None
    assert p["events"][0]["metrics_opened"] is False
