from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ApiFootballRightsBaseline:
    provider_key: str = "api_football"
    provider_terms_reference: str = (
        "https://api-sports.io/terms"
    )
    terms_reviewed_on: str = "2026-08-20"
    direct_data_resale_permitted: bool = False
    provider_publication_license_granted: bool = False
    betting_platform_additional_rights_review_required: bool = True
    competent_rights_holder_review_required: bool = True
    legal_review_required: bool = True
    authorization_status: str = (
        "BLOCKED_PENDING_RIGHTS_REVIEW"
    )
    real_provider_execution_authorized: bool = False

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.api-football-rights-baseline/1"
            ),
            "provider_key": self.provider_key,
            "provider_terms_reference": (
                self.provider_terms_reference
            ),
            "terms_reviewed_on": (
                self.terms_reviewed_on
            ),
            "direct_data_resale_permitted": (
                self.direct_data_resale_permitted
            ),
            "provider_publication_license_granted": (
                self.provider_publication_license_granted
            ),
            "betting_platform_additional_rights_review_required": (
                self.betting_platform_additional_rights_review_required
            ),
            "competent_rights_holder_review_required": (
                self.competent_rights_holder_review_required
            ),
            "legal_review_required": (
                self.legal_review_required
            ),
            "authorization_status": (
                self.authorization_status
            ),
            "real_provider_execution_authorized": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


def api_football_rights_baseline() -> ApiFootballRightsBaseline:
    return ApiFootballRightsBaseline()
