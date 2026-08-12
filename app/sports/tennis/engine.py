from typing import Any

from app.core.interfaces.sport_engine import SportEngine
from app.sports.tennis.data_quality import TennisDataQualityEngine
from app.sports.tennis.match_model import TennisMatchModel
from app.sports.tennis.quality_adapter import TennisQualityAdapter
from app.sports.tennis.processing_result import TennisProcessingResult
from app.sports.tennis.data_coverage import TennisDataCoverage
from app.sports.tennis.coverage_policy import TennisCoveragePolicy
from app.sports.tennis.match_factory import TennisMatchFactory

class TennisEngine(SportEngine):
    """
    Motor especializado de MATRIX TENIS.
    """

    def __init__(self):
        self.data_quality_engine = TennisDataQualityEngine()

    @property
    def sport_code(self) -> str:
        return "TENNIS"

    def validate_match(self, match: Any) -> bool:
        if not isinstance(match, TennisMatchModel):
            return False

        quality_data = TennisQualityAdapter.to_quality_data(match)
        quality_result = self.data_quality_engine.validate_match(quality_data)

        return quality_result.passed

    def calculate_data_confidence(self, coverage: TennisDataCoverage) -> float:
        return coverage.score()


    def process_match(self, match: Any) -> Any:
        if isinstance(match, dict):
            match = TennisMatchFactory.from_dict(match)

        if not self.validate_match(match):
            raise ValueError("El partido no es válido para MATRIX TENIS.")

        return match

    def analyze_match(
        self,
        match: Any,
        coverage: TennisDataCoverage | None = None,
        policy: TennisCoveragePolicy | None = None,
    ) -> TennisProcessingResult:
        if not self.validate_match(match):
            return TennisProcessingResult(
                accepted=False,
                reason="invalid_match",
                confidence=0.0,
            )

        confidence = 0.0

        if coverage is not None:
            confidence = self.calculate_data_confidence(coverage)

        if policy is not None:
            if coverage is None or not policy.accepts(coverage):
                return TennisProcessingResult(
                    accepted=False,
                    reason="insufficient_data_coverage",
                    confidence=0.0,
                )

        return TennisProcessingResult(
            accepted=True,
            reason="valid_match",
            confidence=confidence,
        )