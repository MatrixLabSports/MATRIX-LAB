from __future__ import annotations

import json
from pathlib import Path

from tools.tennis_clay_lane_bootstrap import (
    build_dataset,
    evaluate_elo,
    select_and_evaluate_elo,
)


def test_clay_dataset_is_unique_chronological_and_separate():
    rows,audit = build_dataset()
    assert audit["raw_clay_rows"] == 2989
    assert audit["clean_completed_rows"] == 2848
    assert audit["duplicate_physical_key_groups"] == 0
    assert audit["split_counts"] == {
        "TRAIN": 2056,
        "VALIDATION": 358,
        "FINAL_HISTORICAL_OOS": 434,
    }
    assert all(row["surface"] == "Clay" for row in rows)
    assert all(row["best_of"] == 3 for row in rows)
    assert len({row["physical_event_key"] for row in rows}) == len(rows)
    assert rows == sorted(
        rows,
        key=lambda r: (
            r["tourney_date"],
            r["tourney_id"],
            r["match_num"],
            r["physical_event_key"],
        ),
    )


def test_clay_dataset_orientation_does_not_encode_winner_side():
    rows,_ = build_dataset()
    assert all(row["player_a_id"] <= row["player_b_id"] for row in rows)
    labels = {row["label_a_win"] for row in rows}
    assert labels == {0,1}


def test_elo_final_oos_not_used_for_parameter_selection():
    rows,_ = build_dataset()
    result = select_and_evaluate_elo(rows)
    assert result["candidate_identity"] == "ATP_CHALLENGER_CLAY_ELO_V1"
    assert result["parameter_selection"]["selection_split"] == "VALIDATION"
    assert result["parameter_selection"]["final_historical_oos_not_used_for_selection"] is True
    assert result["final_historical_oos"]["n"] == 434
    assert result["baseline_0_5"]["n"] == 434
    assert result["prospective_holdout_created"] is False
    assert result["prospective_observations"] == 0
    assert result["automatic_promotion"] is False
    assert result["real_money"] == "BLOCKED"
