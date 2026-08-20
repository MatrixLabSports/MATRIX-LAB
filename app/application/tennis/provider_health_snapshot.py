from app.core.provider_health_snapshot import (
    build_provider_health_snapshot,
)


def build_tennis_provider_health_snapshot(
    *,
    provider_key,
    run_ids,
    audit_ledger,
):
    return build_provider_health_snapshot(
        provider_key=provider_key,
        sport="tennis",
        run_ids=run_ids,
        audit_ledger=audit_ledger,
    )
