"""
MATRIX TENIS
Pipeline Engine

Este módulo coordina la ejecución ordenada de todos los motores
principales del sistema.
"""

from dataclasses import dataclass

from app.data.data_quality_engine import MatrixDataQualityEngine
from app.core.contracts.sport_registry import get_sport
from app.core.contracts.sport_contract import SportContract
from app.core.engine_registry import EngineRegistry

@dataclass
class PipelineResult:
    passed: bool
    stage: str
    status: str
    messages: list[str]
    sport: SportContract | None = None
    data: object | None = None

class MatrixPipelineEngine:
    """
    Coordinador principal de MATRIX.
    """

    def __init__(self, engine_registry: EngineRegistry | None = None):
        self.name = "MATRIX PIPELINE ENGINE"
        self.version = "0.1"
        self.data_quality_engine = MatrixDataQualityEngine()
        self.engine_registry = engine_registry

    def process_match(self, match: dict):
        """
        Ejecuta el flujo inicial de procesamiento de un partido.
        """
        sport = get_sport(match.get("sport", ""))
        quality_result = self.data_quality_engine.validate_match(match)

        if not quality_result.passed:
            return PipelineResult(
                passed=False,
                stage="DATA_QUALITY",
                status=quality_result.status,
                messages=quality_result.messages,
                sport=sport,
                data=quality_result,
            )

        if self.engine_registry is not None:
            engine = self.engine_registry.get(sport.code)
            engine.process_match(match)

        return PipelineResult(
            passed=True,
            stage="DATA_QUALITY",
            status=quality_result.status,
            messages=quality_result.messages,
            sport=sport,
            data=quality_result,
        )