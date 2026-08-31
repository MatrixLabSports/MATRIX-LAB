from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    coverage: float
    freshness_ok: bool
    rights_ok: bool
    schema_ok: bool


def governed_failover(primary: ProviderHealth, secondary: ProviderHealth, *, human_approved: bool) -> str:
    if primary.freshness_ok and primary.rights_ok and primary.schema_ok:
        return primary.provider
    if not human_approved:
        raise ValueError("AUTOMATIC_PROVIDER_SWITCH_FORBIDDEN")
    if not (secondary.freshness_ok and secondary.rights_ok and secondary.schema_ok):
        raise ValueError("SECONDARY_PROVIDER_NOT_ADMISSIBLE")
    return secondary.provider
