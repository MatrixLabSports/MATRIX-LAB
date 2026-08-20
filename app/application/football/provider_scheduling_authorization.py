from app.core.provider_scheduling_authorization import (
    authorize_provider_scheduling,
)


def authorize_football_provider_scheduling(
    *,
    queue_manifest,
    health_decisions,
):
    return authorize_provider_scheduling(
        queue_manifest=queue_manifest,
        health_decisions=health_decisions,
        expected_sport="football",
    )
