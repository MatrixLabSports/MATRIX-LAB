from __future__ import annotations

import json
from pathlib import Path

from tools.live_tennis_cross_provider_equivalence import build


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_blocks_without_overlap(tmp_path: Path) -> None:
    root = tmp_path / "live"
    _write(
        root / "2026-10-12" / "MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json",
        {
            "operational_date_bogota": "2026-10-12",
            "states": [{
                "match_id": 1,
                "p1_name": "Alice Smith",
                "p2_name": "Beth Jones",
                "tournament": "W50 Test",
                "round": "Round of 32",
                "surface": "hard",
                "captured_at_utc": "2026-10-12T12:00:00+00:00",
                "settlement_status": "FINAL_STANDARD",
                "p1_match_win": 1,
            }],
        },
    )
    _write(
        root / "2026-10-12" / "MATRIX_LIVE_TENNIS_API_TENNIS_FAILOVER_LEDGER_V1.json",
        {
            "operational_date_bogota": "2026-10-12",
            "states": [{
                "match_id": "x",
                "p1_name": "C. Other",
                "p2_name": "D. Player",
                "tournament": "W50 Test",
                "round": "Round of 32",
                "event_type": "Wta Singles",
                "captured_at_utc": "2026-10-12T12:05:00+00:00",
                "settlement_status": "FINAL_STANDARD",
                "p1_match_win": 1,
            }],
        },
    )
    result = build(root, tmp_path / "audit.json")
    assert result["status"] == "BLOCKED_NO_ADJUDICABLE_CROSS_PROVIDER_OVERLAP"
    assert result["counts"]["participant_pair_plus_tournament_same_day_candidates"] == 0
    assert result["calibration_admission"]["paid_only_events_admitted_to_existing_free_provider_lane"] is False


def test_detects_event_crosswalk_but_does_not_authorize_provider_wide_merge(tmp_path: Path) -> None:
    root = tmp_path / "live"
    _write(
        root / "2026-10-12" / "MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json",
        {
            "operational_date_bogota": "2026-10-12",
            "states": [{
                "match_id": 10,
                "p1_name": "Pablo Carreno Busta",
                "p2_name": "Felix Auger Aliassime",
                "tournament": "Shanghai",
                "round": "Round of 32",
                "surface": "hard",
                "captured_at_utc": "2026-10-12T12:00:00+00:00",
                "settlement_status": "FINAL_STANDARD",
                "p1_match_win": 0,
            }],
        },
    )
    _write(
        root / "2026-10-12" / "MATRIX_LIVE_TENNIS_API_TENNIS_FAILOVER_LEDGER_V1.json",
        {
            "operational_date_bogota": "2026-10-12",
            "states": [{
                "match_id": "99",
                "p1_name": "P. Carreno-Busta",
                "p2_name": "F. Auger-Aliassime",
                "tournament": "ATP Shanghai",
                "round": "ATP Shanghai - 1/16-finals",
                "event_type": "Atp Singles",
                "captured_at_utc": "2026-10-12T12:10:00+00:00",
                "settlement_status": "FINAL_STANDARD",
                "p1_match_win": 0,
            }],
        },
    )
    result = build(root, tmp_path / "audit.json")
    assert result["status"] == "PASS_EXACT_EVENT_CROSSWALKS_PRESENT"
    assert result["counts"]["adjudicable_exact_event_crosswalks"] == 1
    assert result["calibration_admission"]["provider_wide_equivalence_certified"] is False
    assert result["counts"]["states_admitted_to_existing_free_provider_lane"] == 0
