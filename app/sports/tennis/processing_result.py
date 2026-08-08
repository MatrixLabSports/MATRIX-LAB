from dataclasses import dataclass


@dataclass(frozen=True)
class TennisProcessingResult:
    accepted: bool
    reason: str
    confidence: float = 0.0

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "confidence debe estar entre 0.0 y 1.0."
            )