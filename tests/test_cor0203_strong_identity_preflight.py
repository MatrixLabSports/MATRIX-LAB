from tools.cor0203_batch_preflight import partition_batch

HOLDOUT = "A22_POST_AUDIT_VIRGIN_HOLDOUT_V1"
FREEZE = "2026-09-25T12:00:00+00:00"


def player(name, canonical_id, provider_id, rank):
    return {
        "name": name,
        "source_id": canonical_id,
        "provider_player_id": provider_id,
        "identity_binding": "API_TENNIS_TO_STATIC_CUT_STRONG_CROSSWALK",
        "hand": "R",
        "age": 24.0,
        "rank": rank,
        "rank_points": 300,
    }


def state():
    names = ["Player A", "Player B"]
    return {
        "history": {
            "matches": {p: [1, 0, 1, 1, 0] for p in names},
            "overall": {p: [3.0, 5.0] for p in names},
            "surface": {p: {"Hard": [3.0, 5.0]} for p in names},
            "serve": {p: [150.0, 250.0] for p in names},
            "ret": {p: [100.0, 250.0] for p in names},
            "opp_strength": {p: [2.5, 5.0] for p in names},
        },
        "elo_overall": {p: 1500.0 for p in names},
        "elo_surface": {"Hard": {p: 1500.0 for p in names}},
        "glicko_overall": {p: {"r": 1500.0, "rd": 100.0} for p in names},
        "glicko_surface": {"Hard": {p: {"r": 1500.0, "rd": 100.0} for p in names}},
    }


def prefeature():
    return {
        "holdout_id": HOLDOUT,
        "created_before_feature_acquisition": True,
        "starting_observation_count": 10,
        "events": [{"event_id": "strong-e11", "features_loaded": False, "outcome": None, "metrics_opened": False}],
    }


def events():
    return {
        "holdout_id": HOLDOUT,
        "starting_observation_count": 10,
        "control_probability_window1": 0.4967,
        "events": [{
            "event_id": "strong-e11",
            "surface": "Hard",
            "tour_level": "C",
            "target_period": 20260921,
            "event_start_utc": "2026-09-26T14:00:00+00:00",
            "source_provider": "api_tennis",
            "source_snapshot_sha256": "a" * 64,
            "identity_crosswalk_required": True,
            "identity_crosswalk_reference": "MATRIX_COR0203_IDENTITY_CROSSWALK_R800.json",
            "players": [
                player("Player A", "CAN-A", "api-tennis:player:11", 100),
                player("Player B", "CAN-B", "api-tennis:player:22", 120),
            ],
        }],
    }


def static4():
    return {
        "holdout_id": HOLDOUT,
        "events": [{
            "event_id": "strong-e11",
            "players": {
                "Player A": {"source_id": "CAN-A", "provider_player_id": "api-tennis:player:11", "identity_binding": "API_TENNIS_TO_STATIC_CUT_STRONG_CROSSWALK", "hand": "R", "age": 24.0, "rank": 100, "rank_points": 300},
                "Player B": {"source_id": "CAN-B", "provider_player_id": "api-tennis:player:22", "identity_binding": "API_TENNIS_TO_STATIC_CUT_STRONG_CROSSWALK", "hand": "R", "age": 24.0, "rank": 120, "rank_points": 300},
            },
        }],
    }


def run(e=None, s=None):
    return partition_batch(
        prefeature=prefeature(),
        static4=s or static4(),
        events=e or events(),
        state=state(),
        freeze_at_utc=FREEZE,
        expected_starting_count=10,
    )


def test_strong_identity_complete_event_passes():
    result = run()
    assert result["result"] == "PASS"
    assert result["valid_event_ids"] == ["strong-e11"]


def test_missing_canonical_source_id_blocks():
    e = events()
    e["events"][0]["players"][0]["source_id"] = ""
    result = run(e=e)
    assert result["result"] == "ALL_BLOCKED"
    assert "CANONICAL_SOURCE_ID_REQUIRED:Player A" in result["blocked"][0]["blockers"]


def test_missing_provider_player_id_blocks():
    e = events()
    e["events"][0]["players"][0]["provider_player_id"] = ""
    result = run(e=e)
    assert result["result"] == "ALL_BLOCKED"
    assert "PROVIDER_PLAYER_ID_REQUIRED:Player A" in result["blocked"][0]["blockers"]


def test_missing_source_snapshot_sha_blocks():
    e = events()
    e["events"][0]["source_snapshot_sha256"] = ""
    result = run(e=e)
    assert result["result"] == "ALL_BLOCKED"
    assert "SOURCE_SNAPSHOT_SHA_REQUIRED" in result["blocked"][0]["blockers"]


def test_static_provider_id_mismatch_blocks():
    s = static4()
    s["events"][0]["players"]["Player A"]["provider_player_id"] = "api-tennis:player:999"
    result = run(s=s)
    assert result["result"] == "ALL_BLOCKED"
    assert "STATIC4_PROVIDER_ID_MISMATCH:Player A" in result["blocked"][0]["blockers"]
