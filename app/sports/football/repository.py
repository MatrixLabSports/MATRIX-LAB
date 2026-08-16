import json
from pathlib import Path

from app.sports.football.contract import FootballMatchContract
from app.sports.football.match_model import FootballMatchModel


class FootballMatchRepository:
    def __init__(
        self,
        file_path: str = "app/data/football_matches.json",
    ) -> None:
        self.file_path = Path(file_path)

    def save_matches(
        self,
        matches: list[FootballMatchModel],
    ) -> None:
        data = [
            {
                "home_team": match.contract.home_team,
                "away_team": match.contract.away_team,
                "competition": match.contract.competition,
                "country": match.contract.country,
                "season": match.season,
                "round": match.round,
                "datetime": match.datetime,
                "status": match.status,
            }
            for match in matches
        ]

        with self.file_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )

    def load_matches(self) -> list[FootballMatchModel]:
        try:
            with self.file_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)
        except json.JSONDecodeError as error:
            raise ValueError(
                "archivo JSON de fútbol es inválido"
            ) from error

        if not isinstance(data, list):
            raise ValueError(
                "archivo de partidos de fútbol debe contener una lista"
            )

        matches: list[FootballMatchModel] = []

        for item in data:
            contract = FootballMatchContract(
                home_team=item["home_team"],
                away_team=item["away_team"],
                competition=item["competition"],
                country=item["country"],
            )

            matches.append(
                FootballMatchModel(
                    contract=contract,
                    season=item["season"],
                    round=item["round"],
                    datetime=item["datetime"],
                    status=item["status"],
                )
            )

        return matches