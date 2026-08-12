from dataclasses import dataclass


@dataclass(frozen=True)
class TennisHistoricalMatch:
    player: str
    opponent: str
    date: str
    tournament: str
    surface: str
    won: bool
    sets_won: int
    sets_lost: int
    games_won: int
    games_lost: int

    def __post_init__(self):
        player = self.player.strip()
        opponent = self.opponent.strip()

        if not player:
            raise ValueError("player no puede estar vacío.")

        if not opponent:
            raise ValueError("opponent no puede estar vacío.")

        if player.casefold() == opponent.casefold():
            raise ValueError("player y opponent no pueden ser iguales.")