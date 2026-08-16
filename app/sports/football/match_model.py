from dataclasses import dataclass

from app.sports.football.contract import FootballMatchContract


@dataclass(frozen=True)
class FootballMatchModel:
    contract: FootballMatchContract
    season: int
    round: str
    datetime: str
    status: str

    ALLOWED_STATUSES = frozenset(
        {
            "scheduled",
            "live",
            "halftime",
            "finished",
            "postponed",
            "cancelled",
            "abandoned",
        }
    )

    def __post_init__(self):
        if not isinstance(self.season, int) or self.season <= 0:
            raise ValueError(
                "season debe ser un entero positivo."
            )

        normalized_status = self.status.strip().casefold()

        if normalized_status not in self.ALLOWED_STATUSES:
            raise ValueError(
                f"status no permitido para un partido de fútbol: "
                f"{self.status}"
            )

        if not self.round.strip():
            raise ValueError(
                "round no puede estar vacío."
            )

        if not self.datetime.strip():
            raise ValueError(
                "datetime no puede estar vacío."
            )
