from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4


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
    def __post_init__(self) -> None:
        if not isinstance(self.analysis_id, str):
            raise TypeError("analysis_id must be a string")
        try:
            UUID(self.analysis_id)
        except ValueError:
            raise ValueError("analysis_id must be a valid UUID") from None
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.created_at.utcoffset().total_seconds() != 0:
            raise ValueError("created_at must be UTC")
        if not isinstance(self.engine_version, str):
            raise TypeError("engine_version must be a string")
        if not isinstance(self.policy_version, str):
            raise TypeError("policy_version must be a string")
        if not self.engine_version.strip():
            raise ValueError("engine_version must not be empty")
        if not self.policy_version.strip():
            raise ValueError("policy_version must not be empty")
        if self.engine_version != self.engine_version.strip():
            raise ValueError("engine_version must not contain surrounding whitespace")
        if self.policy_version != self.policy_version.strip():
            raise ValueError("policy_version must not contain surrounding whitespace")

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