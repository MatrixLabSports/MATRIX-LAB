from tools.cor0203_production_observability import build_observability_snapshot


def base():
    return {
        "source_readiness": {
            "provider": "api_tennis",
            "ready": True,
            "status": "DISCOVERY_COMPLETED",
            "cause": "READY",
            "network_calls": 3,
        },
        "prereg": {"status": "NO_NEW_EVENTS", "events_registered": 0, "skipped": []},
        "crosswalk": {"crosswalk_revisions": []},
        "stage": {"revisions": []},
        "runner": {
            "starting_physical_count": 10,
            "ending_physical_count": 10,
            "new_freezes": 0,
            "new_blocked": 0,
            "waiting_inputs": [],
        },
        "integrity": {
            "result": "PASS",
            "passed_observations": 10,
            "failed_observations": 0,
            "silent_imputation_detected": False,
            "outcomes_read": 0,
            "metrics_opened": False,
        },
    }


def build(x):
    return build_observability_snapshot(**x)


def test_disconnected_source_never_looks_like_empty_inventory():
    x = base()
    x["source_readiness"] = {
        "provider": "api_tennis",
        "ready": False,
        "status": "API_TENNIS_KEY_NOT_CONFIGURED",
        "cause": "PROVIDER_CREDENTIAL_NOT_CONFIGURED",
        "network_calls": 0,
    }
    result = build(x)
    assert result["operational_state"] == "SOURCE_BLOCKED"
    assert result["bottleneck"] == {
        "stage": "SOURCE",
        "cause": "PROVIDER_CREDENTIAL_NOT_CONFIGURED",
    }
    assert result["source"]["network_calls"] == 0


def test_ready_source_with_no_events_is_valid_idle():
    result = build(base())
    assert result["operational_state"] == "IDLE_VALID"
    assert result["bottleneck"]["stage"] == "INVENTORY"


def test_holdout_targets_are_explicit():
    result = build(base())
    assert result["holdout"]["window1_count"] == 10
    assert result["holdout"]["window1_remaining"] == 190
    assert result["holdout"]["total_count"] == 10
    assert result["holdout"]["total_remaining"] == 590
    assert result["holdout"]["metrics"] == "SEALED_UNTIL_600"


def test_new_freeze_marks_producing():
    x = base()
    x["prereg"] = {"status": "PREREGISTERED", "events_registered": 1, "skipped": []}
    x["runner"]["ending_physical_count"] = 11
    x["runner"]["new_freezes"] = 1
    x["integrity"]["passed_observations"] = 11
    result = build(x)
    assert result["operational_state"] == "PRODUCING"
    assert result["bottleneck"]["cause"] == "NEW_VALID_FREEZES_PRODUCED"
