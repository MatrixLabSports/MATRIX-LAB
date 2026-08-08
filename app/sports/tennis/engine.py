from typing import Any

from app.core.interfaces.sport_engine import SportEngine
from app.sports.tennis.data_quality import TennisDataQualityEngine
from app.sports.tennis.match_model import TennisMatchModel
from app.sports.tennis.quality_adapter import TennisQualityAdapter
from app.sports.tennis.processing_result import TennisProcessingResult

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

    def process_match(self, match: Any) -> Any:
        if not self.validate_match(match):
            raise ValueError("El partido no es válido para MATRIX TENIS.")

        return match

    def analyze_match(self, match: Any) -> TennisProcessingResult:
        if not self.validate_match(match):
            return TennisProcessingResult(
                accepted=False,
                reason="invalid_match",
            )

        return TennisProcessingResult(
            accepted=True,
            reason="valid_match",
        )