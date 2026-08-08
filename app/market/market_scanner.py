from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass
class TennisMatch:
    player_1: str
    player_2: str
    tournament: str
    circuit: str
    surface: str
    round_name: str
    start_time: datetime
    status: str = "scheduled"


class GlobalMatchScanner:
    def __init__(self) -> None:
        self.name = "GLOBAL MATCH SCANNER"
        self.version = "0.1"

    def scan_daily_calendar(self) -> List[TennisMatch]:
        """
        Primera versión de prueba.

        Más adelante esta función se conectará a fuentes reales
        para revisar el calendario mundial ATP, WTA, Challenger e ITF.
        """
        sample_matches = [
            TennisMatch(
                player_1="Michael Zheng",
                player_2="Miomir Kecmanovic",
                tournament="Montreal",
                circuit="ATP",
                surface="Hard",
                round_name="R128",
                start_time=datetime(2026, 8, 3, 10, 5),
            ),
            TennisMatch(
                player_1="Aleksandar Kovacevic",
                player_2="Nuno Borges",
                tournament="Montreal",
                circuit="ATP",
                surface="Hard",
                round_name="R128",
                start_time=datetime(2026, 8, 3, 11, 10),
            ),
        ]

        return sample_matches

    def print_matches(self, matches: List[TennisMatch]) -> None:
        print("=" * 45)
        print(f"{self.name} - VERSION {self.version}")
        print("=" * 45)

        for index, match in enumerate(matches, start=1):
            print(f"\nPARTIDO {index}")
            print(f"Jugador 1: {match.player_1}")
            print(f"Jugador 2: {match.player_2}")
            print(f"Torneo: {match.tournament}")
            print(f"Circuito: {match.circuit}")
            print(f"Superficie: {match.surface}")
            print(f"Ronda: {match.round_name}")
            print(f"Hora: {match.start_time}")
            print(f"Estado: {match.status}")

        print("\nEscaneo diario completado.")


if __name__ == "__main__":
    scanner = GlobalMatchScanner()
    daily_matches = scanner.scan_daily_calendar()
    scanner.print_matches(daily_matches)