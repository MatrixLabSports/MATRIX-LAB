from dataclasses import dataclass
from datetime import datetime
from app.analysis.filter_engine import MatrixFilterEngine
from app.analysis.score_engine import MatrixScoreEngine
from app.data.match_repository import MatchRepository
from app.data.data_quality_engine import MatrixDataQualityEngine
from app.risk.risk_engine import MatrixRiskEngine
from app.reports.report_engine import (
    MatrixReport,
    MatrixReportEngine,
)

@dataclass
class MatchAnalysis:
    player1: str
    player2: str
    tournament: str
    filter_status: str
    filter_score: int
    matrix_score: float
    risk_score: float
    risk_level: str
    level: str
    confidence: str
    decision: str
    warnings: list[str]

    @property
    def score_band_label(self) -> str:
        return self.confidence

class MatrixAnalysisEngine:
    """
    Coordina el repositorio, el filtro y el sistema de puntuación.

    Versión 0.1:
    utiliza métricas de prueba para comprobar la integración.
    No genera todavía apuestas reales.
    """

    def __init__(self) -> None:
        self.name = "MATRIX ANALYSIS ENGINE"
        self.version = "0.1"

        self.repository = MatchRepository()
        self.data_quality_engine = MatrixDataQualityEngine()
        self.filter_engine = MatrixFilterEngine()
        self.score_engine = MatrixScoreEngine()
        self.risk_engine = MatrixRiskEngine()
        self.report_engine = MatrixReportEngine()   

    def analyze_daily_matches(self) -> list[MatchAnalysis]:
        matches = self.repository.load_matches()
        analyses: list[MatchAnalysis] = []

        for match in matches:
            quality_result = self.data_quality_engine.validate_match(match)

            if not quality_result.passed:
                continue
            filter_result = self.filter_engine.evaluate_match(match)
            risk_result = self.risk_engine.evaluate_risk(
                data_risk=10,
                statistical_risk=30,
                sporting_risk=25,
                market_risk=35,
                operational_risk=10,
            )

            if not risk_result.allowed_to_continue:
                continue
            metrics = self._build_test_metrics(
                filter_score=filter_result.score
            )

            score_result = self.score_engine.calculate_score(
                data_quality=metrics["data_quality"],
                recent_form=metrics["recent_form"],
                surface_performance=metrics["surface_performance"],
                market_value=metrics["market_value"],
                risk_control=metrics["risk_control"],
            )

            decision, warnings = self._make_decision(
                filter_status=filter_result.status,
                matrix_score=score_result.total_score,
            )

            analyses.append(
                MatchAnalysis(
                    player1=match["player1"],
                    player2=match["player2"],
                    tournament=match["tournament"],
                    filter_status=filter_result.status,
                    filter_score=filter_result.score,
                    matrix_score=score_result.total_score,
                    risk_score=risk_result.risk_score,
                    risk_level=risk_result.level,  
                    level=score_result.level,
                    confidence=score_result.confidence,
                    decision=decision,
                    warnings=warnings,
                )
            )
            report = MatrixReport(
                created_at=datetime.now().isoformat(timespec="seconds"),
                player1=match["player1"],
                player2=match["player2"],
                tournament=match["tournament"],
                filter_score=filter_result.score,
                matrix_score=score_result.total_score,
                risk_score=risk_result.risk_score,
                risk_level=risk_result.level,
                confidence=score_result.confidence,
                decision=decision,
            )

            self.report_engine.save_report(report)
        return analyses

    def _build_test_metrics(
        self,
        filter_score: int,
    ) -> dict[str, float]:
        """
        Métricas temporales de integración.

        Serán sustituidas después por estadísticas reales,
        cuotas, riesgo, fatiga y rendimiento por superficie.
        """
        base_score = min(filter_score / 7 * 100, 100)

        return {
            "data_quality": base_score,
            "recent_form": 78.0,
            "surface_performance": 82.0,
            "market_value": 76.0,
            "risk_control": 85.0,
        }

    def _make_decision(
        self,
        filter_status: str,
        matrix_score: float,
    ) -> tuple[str, list[str]]:
        warnings: list[str] = [
            "Análisis de prueba: faltan estadísticas y cuotas reales."
        ]

        if filter_status == "DESCARTADO":
            return "DESCARTAR", warnings

        if filter_status == "EN VIGILANCIA":
            return "MANTENER EN VIGILANCIA", warnings

        if matrix_score >= 90:
            return "CANDIDATO PRIORITARIO", warnings

        if matrix_score >= 80:
            return "CANDIDATO PARA REVISIÓN", warnings

        return "NO APOSTAR TODAVÍA", warnings

    def print_report(
        self,
        analyses: list[MatchAnalysis],
    ) -> None:
        print("=" * 55)
        print(f"{self.name} - VERSION {self.version}")
        print("=" * 55)

        for index, analysis in enumerate(analyses, start=1):
            print(f"\nPARTIDO {index}")
            print(
                f"{analysis.player1} vs "
                f"{analysis.player2}"
            )
            print(f"Torneo: {analysis.tournament}")
            print(
                f"Filtro: {analysis.filter_status} "
                f"({analysis.filter_score}/7)"
            )
            print(
                f"MATRIX Score: "
                f"{analysis.matrix_score}/100"
            )
            print(
                f"Riesgo MATRIX: "
                f"{analysis.risk_score}/100"
            )
            print(f"Nivel de riesgo: {analysis.risk_level}")
            print(f"Nivel: {analysis.level}")
            print(f"Confianza: {analysis.confidence}")
            print(f"Decisión: {analysis.decision}")
            print("Advertencias:")

            for warning in analysis.warnings:
                print(f"- {warning}")

        print("\nAnálisis diario completado.")


if __name__ == "__main__":
    engine = MatrixAnalysisEngine()

    try:
        daily_analyses = engine.analyze_daily_matches()
        engine.print_report(daily_analyses)

    except (FileNotFoundError, ValueError) as error:
        print(f"\nERROR DE MATRIX: {error}")