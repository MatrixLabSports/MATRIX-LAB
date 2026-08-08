from dataclasses import dataclass


@dataclass(frozen=True)
class TennisMatchContract:
    player1: str
    player2: str
    tournament: str
    surface: str

    def __post_init__(self):
        player1 = self.player1.strip()
        player2 = self.player2.strip()
        tournament = self.tournament.strip()

        surface = self.surface.strip()

        if not player1 or not player2:
            raise ValueError("player1 y player2 no pueden estar vacíos.")

        if not tournament:
            raise ValueError("tournament no puede estar vacío.")

        if not surface:
            raise ValueError("surface no puede estar vacía.")

        if player1.casefold() == player2.casefold():
            raise ValueError("player1 y player2 no pueden ser iguales.")