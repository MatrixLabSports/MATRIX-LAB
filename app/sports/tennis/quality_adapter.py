from app.sports.tennis.match_model import TennisMatchModel


class TennisQualityAdapter:
    """
    Adapta TennisMatchModel al formato requerido
    por TennisDataQualityEngine.
    """

    @staticmethod
    def to_quality_data(match: TennisMatchModel) -> dict[str, str]:
        return {
            "player1": match.contract.player1,
            "player2": match.contract.player2,
            "surface": match.contract.surface,
        }