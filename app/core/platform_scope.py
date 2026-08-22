from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformScope:
    scope_id: str
    private_internal_only: bool
    commercial_use: bool
    public_redistribution: bool
    data_resale: bool
    customer_display: bool
    sublicensing: bool
    internal_analytics: bool
    internal_modeling: bool
    internal_dashboard: bool
    private_research: bool
    automatic_provider_switch: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def payload(self) -> dict[str, object]:
        return {
            "scope_id": self.scope_id,
            "private_internal_only": self.private_internal_only,
            "commercial_use": self.commercial_use,
            "public_redistribution": self.public_redistribution,
            "data_resale": self.data_resale,
            "customer_display": self.customer_display,
            "sublicensing": self.sublicensing,
            "internal_analytics": self.internal_analytics,
            "internal_modeling": self.internal_modeling,
            "internal_dashboard": self.internal_dashboard,
            "private_research": self.private_research,
            "automatic_provider_switch": self.automatic_provider_switch,
            "automatic_model_promotion": self.automatic_model_promotion,
            "automatic_wagering": self.automatic_wagering,
        }


PRIVATE_INTERNAL_ONLY = PlatformScope(
    scope_id="PRIVATE_INTERNAL_ONLY",
    private_internal_only=True,
    commercial_use=False,
    public_redistribution=False,
    data_resale=False,
    customer_display=False,
    sublicensing=False,
    internal_analytics=True,
    internal_modeling=True,
    internal_dashboard=True,
    private_research=True,
)


def require_private_internal_only(
    scope: PlatformScope,
) -> PlatformScope:
    if not isinstance(scope, PlatformScope):
        raise ValueError("PLATFORM_SCOPE_TYPE_REQUIRED")

    expected = PRIVATE_INTERNAL_ONLY.payload()
    if scope.payload() != expected:
        raise ValueError("PRIVATE_INTERNAL_ONLY_SCOPE_REQUIRED")

    return scope
