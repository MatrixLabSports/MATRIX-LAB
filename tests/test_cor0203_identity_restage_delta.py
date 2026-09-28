import json
from pathlib import Path

from tools.cor0203_identity_restage_delta import build_identity_restage_delta


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload)+"\n", encoding="utf-8")


def test_creates_append_only_delta_for_newly_unblocked_unstaged_event(tmp_path):
    runtime=tmp_path/"runtime"
    holdout=tmp_path/"holdout"
    runtime.mkdir(); holdout.mkdir()
    pre={
        "revision":"R10",
        "holdout_id":"A22_POST_AUDIT_VIRGIN_HOLDOUT_V1",
        "events":[
            {"event_id":"E1","outcome":None,"metrics_opened":False,"features_loaded":False},
            {"event_id":"E2","outcome":None,"metrics_opened":False,"features_loaded":False},
        ],
    }
    _write(runtime/"MATRIX_COR0203_PREFEATURE_REGISTRY_R10.json",pre)
    _write(runtime/"MATRIX_COR0203_IDENTITY_CROSSWALK_R10.json",{
        "events":[{"event_id":"E1","status":"PASS"},{"event_id":"E2","status":"PASS"}]
    })
    _write(runtime/"MATRIX_COR0203_PROSPECTIVE_EVENTS_R10.json",{"events":[{"event_id":"E1"}]})
    result=build_identity_restage_delta(runtime_dir=runtime,holdout_dir=holdout)
    assert result["created"] is True
    assert result["revision"]==11
    assert result["event_ids"]==["E2"]
    delta=json.loads((runtime/"MATRIX_COR0203_PREFEATURE_REGISTRY_R11.json").read_text())
    assert delta["new_event_selection"] is False
    assert delta["selection_unchanged_from_original_preregistration"] is True
    assert delta["events"][0]["restage_original_revision"]=="R10"


def test_does_not_duplicate_frozen_or_already_staged_events(tmp_path):
    runtime=tmp_path/"runtime"
    holdout=tmp_path/"holdout"
    runtime.mkdir(); holdout.mkdir()
    _write(runtime/"MATRIX_COR0203_PREFEATURE_REGISTRY_R10.json",{
        "events":[
            {"event_id":"E1","outcome":None,"metrics_opened":False,"features_loaded":False},
            {"event_id":"E2","outcome":None,"metrics_opened":False,"features_loaded":False},
        ]
    })
    _write(runtime/"MATRIX_COR0203_IDENTITY_CROSSWALK_R10.json",{
        "events":[{"event_id":"E1","status":"PASS"},{"event_id":"E2","status":"PASS"}]
    })
    _write(runtime/"MATRIX_COR0203_PROSPECTIVE_EVENTS_R9.json",{"events":[{"event_id":"E1"}]})
    _write(holdout/"MATRIX_COR0203_HOLDOUT_BATCH_R9.json",{"observations":[{"event_id":"E2"}]})
    result=build_identity_restage_delta(runtime_dir=runtime,holdout_dir=holdout)
    assert result["created"] is False
    assert result["events"]==0


def test_delta_start_count_uses_physical_ending_count_not_raw_event_count(tmp_path):
    runtime=tmp_path/"runtime"
    holdout=tmp_path/"holdout"
    runtime.mkdir(); holdout.mkdir()
    _write(runtime/"MATRIX_COR0203_PREFEATURE_REGISTRY_R10.json",{
        "events":[{"event_id":"E3","outcome":None,"metrics_opened":False,"features_loaded":False}]
    })
    _write(runtime/"MATRIX_COR0203_IDENTITY_CROSSWALK_R10.json",{
        "events":[{"event_id":"E3","status":"PASS"}]
    })
    _write(holdout/"MATRIX_COR0203_HOLDOUT_BATCH_R1.json",{
        "ending_observation_count":44,
        "observations":[{"event_id":"OLD1"},{"event_id":"OLD2"}]
    })
    result=build_identity_restage_delta(runtime_dir=runtime,holdout_dir=holdout)
    delta=json.loads((runtime/"MATRIX_COR0203_PREFEATURE_REGISTRY_R11.json").read_text())
    assert result["created"] is True
    assert delta["starting_observation_count"]==44
