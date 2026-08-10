from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class TennisAnalysisContext:
    """
    Contexto auditable e inmutable de una ejecución de análisis
    de MATRIX TENIS.
    """

    analysis_id: str
    created_at: datetime
    engine_version: str
    policy_version: str

    @classmethod
    def create(
        cls,
        engine_version: str,
        policy_version: str,
    ) -> "TennisAnalysisContext":
        return cls(
            analysis_id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            engine_version=engine_version,
            policy_version=policy_version,
        )

    def test_tennis_analysis_context_created_at_is_utc():
        context = TennisAnalysisContext.create(
            engine_version="0.1.0",
            policy_version="0.1.0",
        )

        assert context.created_at.tzinfo is not None
        assert context.created_at.utcoffset().total_seconds() == 0