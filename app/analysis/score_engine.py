from dataclasses import dataclass


@dataclass
class ScoreResult:
    total_score: float
    level: str
    confidence: str

    @property
    def score_band_label(self) -> str:
        return self.confidence


class MatrixScoreEngine:
    def __init__(self) -> None:
        self.name = "MATRIX SCORE ENGINE"
        self.version = "0.1"

    def calculate_score(
        self,
        data_quality: float,
        recent_form: float,
        surface_performance: float,
        market_value: float,
        risk_control: float,
    ) -> ScoreResult:
        weights = {
            "data_quality": 0.20,
            "recent_form": 0.20,
            "surface_performance": 0.20,
            "market_value": 0.25,
            "risk_control": 0.15,
        }

        total_score = (
            data_quality * weights["data_quality"]
            + recent_form * weights["recent_form"]
            + surface_performance * weights["surface_performance"]
            + market_value * weights["market_value"]
            + risk_control * weights["risk_control"]
        )

        level, confidence = self._classify_score(total_score)

        return ScoreResult(
            total_score=round(total_score, 2),
            level=level,
            confidence=confidence,
        )

    def _classify_score(self, score: float) -> tuple[str, str]:
        if score >= 90:
            return "A+", "MUY ALTA"
        if score >= 80:
            return "A", "ALTA"
        if score >= 70:
            return "B", "MEDIA"
        if score >= 60:
            return "C", "BAJA"

        return "D", "NO APROBADA"


if __name__ == "__main__":
    engine = MatrixScoreEngine()

    result = engine.calculate_score(
        data_quality=95,
        recent_form=88,
        surface_performance=92,
        market_value=90,
        risk_control=85,
    )

    print("=" * 45)
    print(f"{engine.name} - VERSION {engine.version}")
    print("=" * 45)
    print(f"Puntuación total: {result.total_score}/100")
    print(f"Nivel: {result.level}")
    print(f"Banda del score: {result.score_band_label}")
