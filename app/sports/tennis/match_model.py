from dataclasses import dataclass

from app.sports.tennis.contract import TennisMatchContract


@dataclass(frozen=True)
class TennisMatchModel:
    contract: TennisMatchContract
    tour: str
    round: str
    datetime: str
    status: str

    ALLOWED_STATUSES = frozenset(
        {
            "scheduled",
            "live",
            "finished",
            "retired",
            "walkover",
            "cancelled",
        }
    )

    ALLOWED_ROUNDS = frozenset(
    {
        "Q1",
        "Q2",
        "Q3",
        "R128",
        "R64",
        "R32",
        "R16",
        "QF",
        "SF",
        "F",
    }
)

    def __post_init__(self):
        normalized_status = self.status.strip().casefold()

        if normalized_status not in self.ALLOWED_STATUSES:
            raise ValueError(
                f"status no permitido para un partido de tenis: {self.status}"
            )

        normalized_round = self.round.strip().upper()

        if normalized_round not in self.ALLOWED_ROUNDS:
            raise ValueError(
                f"round no permitido para un partido de tenis: {self.round}"
            )