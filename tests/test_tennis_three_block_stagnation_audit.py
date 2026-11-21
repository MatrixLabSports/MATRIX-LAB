from tools.tennis_three_block_stagnation_audit import classify_reason


def test_duplicate_is_never_recovered_as_new_observation():
    cat, rec, sources = classify_reason("EVENT_ALREADY_FROZEN")
    assert cat == "DUPLICATE_OR_ALREADY_FROZEN"
    assert rec == "NOT_RECOVERABLE_AS_NEW_OBSERVATION"
    assert sources == []


def test_identity_blocker_has_governed_recovery_chain():
    cat, rec, sources = classify_reason("IDENTITY_CROSSWALK_MISSING:rapidapi-tennis:player:1")
    assert cat == "IDENTITY"
    assert rec == "RECOVERABLE_IF_PREMATCH_AND_EVIDENCE_EXISTS"
    assert sources[:3] == ["SofaScore", "Flashscore", "RapidAPI Tennis"]


def test_pit_blocker_requires_causal_history():
    cat, rec, _ = classify_reason("PIT_CATCHUP_NOT_READY:rapidapi-tennis:player:2")
    assert cat == "PIT_OR_SURFACE_HISTORY"
    assert rec == "RECOVERABLE_ONLY_WITH_CAUSAL_PREMATCH_HISTORY"


def test_post_start_is_never_backfilled():
    cat, rec, sources = classify_reason("POST_START_FREEZE_FORBIDDEN")
    assert cat == "TIMING"
    assert rec == "NOT_RECOVERABLE_NO_BACKFILL"
    assert sources == []
