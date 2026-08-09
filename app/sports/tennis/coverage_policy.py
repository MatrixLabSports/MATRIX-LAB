from dataclasses import dataclass

from app.sports.tennis.data_coverage import TennisDataCoverage


@dataclass(frozen=True)
class TennisCoveragePolicy:
    """
    Política que decide si la cobertura de datos de un partido
    es suficiente para permitir un análisis de MATRIX TENIS.
    """

    minimum_score: float = 0.5

    def __post_init__(self) -> None:
        if isinstance(self.minimum_score, bool):
            raise TypeError("minimum_score must be numeric")

        if not isinstance(self.minimum_score, (int, float)):
            raise TypeError("minimum_score must be numeric")

        if not 0.0 <= self.minimum_score <= 1.0:
            raise ValueError("minimum_score must be between 0.0 and 1.0")

    def accepts(self, coverage: TennisDataCoverage) -> bool:
        if not isinstance(coverage, TennisDataCoverage):
            raise TypeError("coverage must be TennisDataCoverage")

        return coverage.score() >= self.minimum_score