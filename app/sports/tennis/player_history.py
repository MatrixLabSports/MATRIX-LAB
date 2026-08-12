from dataclasses import dataclass

from app.sports.tennis.historical_match import TennisHistoricalMatch


@dataclass(frozen=True)
class TennisPlayerHistory:
    player: str
    matches: tuple[TennisHistoricalMatch, ...] = ()

    def __post_init__(self):
        player = self.player.strip()

        if not player:
            raise ValueError("player no puede estar vacío.")

    def recent_matches(self, limit: int) -> tuple[TennisHistoricalMatch, ...]:
        if limit <= 0:
            raise ValueError("limit debe ser mayor que cero.")

        ordered_matches = sorted(
            self.matches,
            key=lambda match: match.date,
            reverse=True,
        )

        return tuple(ordered_matches[:limit])

    STANDARD_WINDOWS = frozenset({5, 10, 20, 30, 50})

    def window(
        self,
        size: int,
    ) -> tuple[TennisHistoricalMatch, ...]:
        if size not in self.STANDARD_WINDOWS:
            raise ValueError(
                "size debe ser una ventana estándar: 5, 10, 20, 30 o 50."
            )

        return self.recent_matches(size)