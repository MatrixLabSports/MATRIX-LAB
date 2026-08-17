import json
from pathlib import Path

from app.sports.football.contract import FootballMatchContract
from app.sports.football.match_model import FootballMatchModel
from app.sports.football.external_identity import ExternalMatchIdentity
from app.sports.football.match_record import FootballMatchRecord
from app.sports.football.sync_state import FootballSyncState


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


    def upsert_records(
        self,
        records: list[FootballMatchRecord],
    ) -> None:
        existing_records: list[FootballMatchRecord] = []

        if self.file_path.exists():
            existing_records = self.load_records()

        records_by_identity = {
            record.identity: record
            for record in existing_records
        }

        for record in records:
            records_by_identity[record.identity] = record

        merged_records = list(records_by_identity.values())

        data = [
            {
                "provider": record.identity.provider,
                "external_id": record.identity.external_id,
                "home_team": record.match.contract.home_team,
                "away_team": record.match.contract.away_team,
                "competition": record.match.contract.competition,
                "country": record.match.contract.country,
                "season": record.match.season,
                "round": record.match.round,
                "datetime": record.match.datetime,
                "status": record.match.status,
                "sync_state": record.sync_state.status,
            }
            for record in merged_records
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


    def load_records(self) -> list[FootballMatchRecord]:
        with self.file_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        records: list[FootballMatchRecord] = []

        for item in data:
            identity = ExternalMatchIdentity(
                provider=item["provider"],
                external_id=item["external_id"],
            )

            contract = FootballMatchContract(
                home_team=item["home_team"],
                away_team=item["away_team"],
                competition=item["competition"],
                country=item["country"],
            )

            match = FootballMatchModel(
                contract=contract,
                season=item["season"],
                round=item["round"],
                datetime=item["datetime"],
                status=item["status"],
            )

            sync_state = FootballSyncState(
                status=item.get(
                    "sync_state",
                    "seen_current_sync",
                ),
            )

            records.append(
                FootballMatchRecord(
                    identity=identity,
                    match=match,
                    sync_state=sync_state,
                )
            )

        return records
