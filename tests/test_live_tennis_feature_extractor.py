from tools.live_tennis_feature_extractor import build_feature_ledger, point_code


def _lab():
    return {
        "candidates": [{
            "match": {
                "id": 200549,
                "tour": "itf",
                "tournament": "ITF W35 Las Vegas, NV 2 Women",
                "round": "Qualifications",
                "round_code": "Q",
                "surface": "hard",
                "p1_name": "Anna Pushkareva",
                "p2_name": "Duru Soke",
                "p1_ranking": 939,
                "p2_ranking": 792,
            }
        }]
    }


def _snap(seq, points, captured):
    return {
        "captured_at_utc": captured,
        "http_status": 200,
        "response_sha256": f"sha-{seq}-{captured}",
        "score": {
            "sets": [0, 1],
            "games": [[3, 1], [6, 4]],
            "points": points,
            "server": 1,
            "sequence": seq,
            "stale": False,
            "origin": "observed",
            "is_tiebreak": False,
            "deciding_set": {"rule": "match_tiebreak", "basis": "inferred"},
            "age_seconds": 4,
            "observed_age_seconds": 2,
            "corroborated": True,
            "sources_count": 2,
            "timestamp": captured,
            "accepted_at": captured,
        },
    }


def test_point_code_preserves_missing():
    assert point_code("0") == 0
    assert point_code("15") == 1
    assert point_code("40") == 3
    assert point_code("AD") == 4
    assert point_code(None) is None
    assert point_code("UNKNOWN") is None


def test_duplicate_sequences_are_quarantined():
    micro = {
        "match_id": 200549,
        "snapshots": [
            _snap(104, ["30", "30"], "2026-10-06T18:43:46+00:00"),
            _snap(104, ["30", "30"], "2026-10-06T18:43:56+00:00"),
            _snap(105, ["30", "40"], "2026-10-06T18:44:06+00:00"),
            _snap(105, ["30", "40"], "2026-10-06T18:44:16+00:00"),
            _snap(105, ["30", "40"], "2026-10-06T18:44:27+00:00"),
            _snap(106, ["40", "40"], "2026-10-06T18:44:37+00:00"),
        ],
    }
    out = build_feature_ledger(_lab(), micro)
    assert out["raw_snapshot_count"] == 6
    assert out["unique_state_count"] == 3
    assert out["duplicate_transport_snapshots_quarantined"] == 3
    assert [x["sequence"] for x in out["states"]] == [104, 105, 106]
    assert [x["captured_at_utc"] for x in out["states"]] == [
        "2026-10-06T18:43:46+00:00",
        "2026-10-06T18:44:06+00:00",
        "2026-10-06T18:44:37+00:00",
    ]


def test_feature_orientation_and_no_label_leakage():
    micro = {"match_id": 200549, "snapshots": [_snap(104, ["30", "40"], "2026-10-06T18:43:46+00:00")]}
    state = build_feature_ledger(_lab(), micro)["states"][0]
    assert state["set_diff_p1"] == -1
    assert state["total_games_p1"] == 4
    assert state["total_games_p2"] == 10
    assert state["total_game_diff_p1"] == -6
    assert state["current_set_game_diff_p1"] == -3
    assert state["point_diff_p1"] == -1
    assert state["server_is_p1"] is True
    assert state["ranking_advantage_p1"] == -147
    assert state["p1_match_win"] is None
    assert state["settlement_status"] == "PENDING_FINAL"
    assert state["label_opened"] is False
