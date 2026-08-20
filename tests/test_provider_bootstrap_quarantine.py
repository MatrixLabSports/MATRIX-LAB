from types import SimpleNamespace

from app.core.provider_bootstrap_quarantine import (
    execute_bootstrap_probe,
    summarize_bootstrap_payload,
)


def test_bootstrap_summary_exposes_shape_not_raw_values():
    summary = summarize_bootstrap_payload(
        {
            "response": [
                {
                    "token": (
                        "synthetic-fixture-value"
                    )
                }
            ],
            "results": 1,
        }
    )

    rendered = repr(summary)

    assert (
        "synthetic-fixture-value"
        not in rendered
    )
    assert summary.raw_payload_retained is False
    assert summary.production_admissible is False
    assert (
        summary.retroactive_promotion_allowed
        is False
    )


def test_bootstrap_probe_is_mode_bound_and_quarantined():
    class Client:
        def get(
            self,
            endpoint,
            params=None,
        ):
            return {
                "response": [
                    {"id": 1}
                ]
            }

    summary = execute_bootstrap_probe(
        authority=SimpleNamespace(
            mode="BOOTSTRAP_PROBE"
        ),
        client=Client(),
        endpoint="status",
    )

    assert (
        summary.status
        == "QUARANTINED_PROBE_ONLY"
    )

    try:
        execute_bootstrap_probe(
            authority=SimpleNamespace(
                mode="PRODUCTION"
            ),
            client=Client(),
            endpoint="status",
        )
    except ValueError as error:
        assert str(error) == (
            "BOOTSTRAP_PROBE_MODE_REQUIRED"
        )
    else:
        raise AssertionError(
            "production cannot use bootstrap probe"
        )
