from app.sports.tennis.contract import TennisMatchContract
from app.sports.tennis.match_model import TennisMatchModel


class TennisMatchFactory:
    @staticmethod
    def from_dict(data: dict) -> TennisMatchModel:
        contract = TennisMatchContract(
            player1=data["player1"],
            player2=data["player2"],
            tournament=data["tournament"],
            surface=data["surface"],
        )

        return TennisMatchModel(
            contract=contract,
            tour=data["tour"],
            round=data["round"],
            datetime=data["datetime"],
            status=data["status"],
        )
