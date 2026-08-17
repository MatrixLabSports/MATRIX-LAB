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
    consecutive_missing_count: int = 0


    def __post_init__(self):
        if (
            not isinstance(self.consecutive_missing_count, int)
            or self.consecutive_missing_count < 0
        ):
            raise ValueError(
                "consecutive_missing_count debe ser un entero no negativo"
            )
