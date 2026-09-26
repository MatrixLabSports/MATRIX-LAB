from __future__ import annotations

import json
from pathlib import Path

import tools.cor0203_batch_runner as runner


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _manifest(revision: int, start: int, event_id: str):
    return {
        "holdout_id": "H",
        "starting_observation_count": start,
        "control_probability_window1": 0.5,
        "events": [
            {
                "event_id": event_id,
                "target_period": 20260921,
                "event_start_utc": "2026-09-30T12:00:00+00:00",
                "surface": "Hard",
                "tour_level": "C",
                "players": [
                    {"name": "A", "hand": "R", "age": 20, "rank": 100, "rank_points": 300},
                    {"name": "B", "hand": "R", "age": 21, "rank": 120, "rank_points": 250},
                ],
            }
        ],
    }


def _pre(start: int, event_id: str):
    return {
        "holdout_id": "H",
        "created_before_feature_acquisition": True,
        "starting_observation_count": start,
        "events": [
            {
                "event_id": event_id,
                "features_loaded": False,
                "outcome": None,
                "metrics_opened": False,
            }
        ],
    }


def _static(event_id: str):
    return {
        "holdout_id": "H",
        "event_id": event_id,
        "players": {
            "A": {"hand": "R", "age": 20, "rank": 100, "rank_points": 300},
            "B": {"hand": "R", "age": 21, "rank": 120, "rank_points": 250},
        },
    }


def _existing_holdout(path: Path, count: int, event_id: str):
    _write(
        path,
        {
            "starting_observation_count": count - 1,
            "added_observations": 1,
            "ending_observation_count": count,
            "observations": [{"event_id": event_id}],
        },
    )


def test_runner_processes_multiple_pending_revisions_and_rebases_count(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    runtime.mkdir()
    holdout.mkdir()
    _existing_holdout(holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R700.json", 9, "old")

    for rev, event_id in [(800, "e10"), (801, "e11")]:
        _write(runtime / f"MATRIX_COR0203_PROSPECTIVE_EVENTS_R{rev}.json", _manifest(rev, 9, event_id))
        _write(runtime / f"MATRIX_COR0203_PREFEATURE_REGISTRY_R{rev}.json", _pre(9, event_id))
        _write(runtime / f"MATRIX_COR0203_STATIC4_R{rev}.json", _static(event_id))

    annual = tmp_path / "annual.csv"
    annual.write_text("tourney_date\n", encoding="utf-8")
    state = tmp_path / "state"
    state.write_text("x", encoding="utf-8")
    bundle = tmp_path / "bundle"
    bundle.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(runner, "_state_for_period", lambda *args: ({}, 0, 0))

    expected_starts = []

    def fake_partition(**kwargs):
        event = kwargs["events"]["events"][0]
        start = kwargs["expected_starting_count"]
        expected_starts.append(start)
        filtered = dict(kwargs["events"])
        filtered["starting_observation_count"] = start
        return {
            "declared_starting_observation_count": kwargs["events"]["starting_observation_count"],
            "starting_observation_count": start,
            "count_rebased_at_freeze": start != kwargs["events"]["starting_observation_count"],
            "input_events": 1,
            "valid_events": 1,
            "blocked_events": 0,
            "valid_event_ids": [event["event_id"]],
            "blocked": [],
            "history_players": {},
            "same_period_results_used": False,
            "silent_imputation_allowed": False,
            "result": "PASS",
            "filtered_manifest": filtered,
        }

    monkeypatch.setattr(runner, "partition_batch", fake_partition)

    def fake_run(command, check):
        assert check is True
        out_path = Path(command[command.index("--out") + 1])
        filtered_path = Path(command[command.index("--events") + 1])
        filtered = json.loads(filtered_path.read_text())
        start = filtered["starting_observation_count"]
        event_id = filtered["events"][0]["event_id"]
        _write(
            out_path,
            {
                "starting_observation_count": start,
                "added_observations": 1,
                "ending_observation_count": start + 1,
                "metrics": "SEALED_UNTIL_600",
                "outcomes_read": 0,
                "observations": [{"event_id": event_id}],
            },
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_pending_batches(
        runtime_dir=runtime,
        holdout_dir=holdout,
        state_b64=state,
        bundle=bundle,
        annual_2026=annual,
        trigger_sha="abc",
    )

    assert expected_starts == [9, 10]
    assert result["new_freezes"] == 2
    assert result["starting_physical_count"] == 9
    assert result["ending_physical_count"] == 11


def test_incomplete_revision_does_not_block_later_complete_revision(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    holdout = tmp_path / "holdout"
    runtime.mkdir()
    holdout.mkdir()
    _existing_holdout(holdout / "MATRIX_COR0203_HOLDOUT_BATCH_R700.json", 9, "old")

    _write(runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R800.json", _manifest(800, 9, "missing-static"))
    _write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R800.json", _pre(9, "missing-static"))

    _write(runtime / "MATRIX_COR0203_PROSPECTIVE_EVENTS_R801.json", _manifest(801, 9, "good"))
    _write(runtime / "MATRIX_COR0203_PREFEATURE_REGISTRY_R801.json", _pre(9, "good"))
    _write(runtime / "MATRIX_COR0203_STATIC4_R801.json", _static("good"))

    annual = tmp_path / "annual.csv"
    annual.write_text("tourney_date\n", encoding="utf-8")
    state = tmp_path / "state"
    state.write_text("x", encoding="utf-8")
    bundle = tmp_path / "bundle"
    bundle.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(runner, "_state_for_period", lambda *args: ({}, 0, 0))

    def fake_partition(**kwargs):
        event = kwargs["events"]["events"][0]
        filtered = dict(kwargs["events"])
        filtered["starting_observation_count"] = kwargs["expected_starting_count"]
        return {
            "declared_starting_observation_count": kwargs["events"]["starting_observation_count"],
            "starting_observation_count": kwargs["expected_starting_count"],
            "count_rebased_at_freeze": False,
            "input_events": 1,
            "valid_events": 1,
            "blocked_events": 0,
            "valid_event_ids": [event["event_id"]],
            "blocked": [],
            "history_players": {},
            "same_period_results_used": False,
            "silent_imputation_allowed": False,
            "result": "PASS",
            "filtered_manifest": filtered,
        }

    monkeypatch.setattr(runner, "partition_batch", fake_partition)

    def fake_run(command, check):
        out_path = Path(command[command.index("--out") + 1])
        filtered_path = Path(command[command.index("--events") + 1])
        filtered = json.loads(filtered_path.read_text())
        start = filtered["starting_observation_count"]
        event_id = filtered["events"][0]["event_id"]
        _write(
            out_path,
            {
                "starting_observation_count": start,
                "added_observations": 1,
                "ending_observation_count": start + 1,
                "metrics": "SEALED_UNTIL_600",
                "outcomes_read": 0,
                "observations": [{"event_id": event_id}],
            },
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_pending_batches(
        runtime_dir=runtime,
        holdout_dir=holdout,
        state_b64=state,
        bundle=bundle,
        annual_2026=annual,
        trigger_sha="abc",
    )

    assert result["waiting_inputs"] == [
        {"revision": 800, "missing": ["MATRIX_COR0203_STATIC4_R800.json"]}
    ]
    assert result["new_freezes"] == 1
    assert result["ending_physical_count"] == 10
    assert (runtime / "MATRIX_COR0203_BATCH_PREFLIGHT_R800.json").exists()
