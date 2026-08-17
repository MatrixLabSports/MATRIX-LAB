from dataclasses import dataclass, field

from app.sports.football.external_identity import ExternalMatchIdentity
from app.sports.football.match_model import FootballMatchModel
from app.sports.football.sync_state import FootballSyncState


@dataclass(frozen=True)
class FootballMatchRecord:
    identity: ExternalMatchIdentity
    match: FootballMatchModel
    sync_state: FootballSyncState = field(
        default_factory=lambda: FootballSyncState(
            status="seen_current_sync",
        )
    )