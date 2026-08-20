from app.application.football.audited_acquisition_execution import (
    execute_audited_football_acquisition_queue,
)
from app.core.provider_execution_authorization import (
    execute_with_provider_authorization,
)


def execute_governed_football_acquisition_queue(
    *,
    queue_manifest,
    authorization_fingerprint,
    scheduling_evidence_ledger,
    health_evidence_ledger,
    **execution_kwargs,
):
    return execute_with_provider_authorization(
        queue_manifest=queue_manifest,
        authorization_fingerprint=authorization_fingerprint,
        scheduling_evidence_ledger=scheduling_evidence_ledger,
        health_evidence_ledger=health_evidence_ledger,
        executor=execute_audited_football_acquisition_queue,
        executor_kwargs=execution_kwargs,
        expected_sport="football",
    )
