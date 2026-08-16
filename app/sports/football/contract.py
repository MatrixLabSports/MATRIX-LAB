from dataclasses import dataclass


@dataclass(frozen=True)
class FootballMatchContract:
    home_team: str
    away_team: str
    competition: str
    country: str

    def __post_init__(self):
        home_team = self.home_team.strip()
        away_team = self.away_team.strip()
        competition = self.competition.strip()
        country = self.country.strip()

        if not home_team or not away_team:
            raise ValueError(
                "home_team y away_team no pueden estar vacíos."
            )

        if not competition:
            raise ValueError(
                "competition no puede estar vacío."
            )

        if not country:
            raise ValueError(
                "country no puede estar vacío."
            )

        if home_team.casefold() == away_team.casefold():
            raise ValueError(
                "home_team y away_team no pueden ser iguales."
            )