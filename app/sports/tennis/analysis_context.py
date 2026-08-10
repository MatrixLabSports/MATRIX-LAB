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
        if not engine_version.strip():
            raise ValueError("engine_version must not be empty")
    
        return cls(
            analysis_id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            engine_version=engine_version,
            policy_version=policy_version,
        )