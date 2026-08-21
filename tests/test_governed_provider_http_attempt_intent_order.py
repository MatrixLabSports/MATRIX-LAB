from pathlib import Path


def test_production_http_boundary_persists_attempt_intent_before_permit_consumption():
    source = Path(
        "app/core/governed_provider_http.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    intent = source.index(
        "persist_attempt_intent("
    )

    consume = source.index(
        "self.network_permit_store.consume"
    )

    started = source.index(
        'event_type="NETWORK_CALL_STARTED"'
    )

    assert intent < consume < started
    assert (
        "ATTEMPT_INTENT_PERSISTENCE_REQUIRED"
        in source
    )
