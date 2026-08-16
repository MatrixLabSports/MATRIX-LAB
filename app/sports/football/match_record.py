from dataclasses import dataclass

from app.sports.football.external_identity import ExternalMatchIdentity
from app.sports.football.match_model import FootballMatchModel


@dataclass(frozen=True)
class FootballMatchRecord:
    identity: ExternalMatchIdentity
    match: FootballMatchModel