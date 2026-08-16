from dataclasses import dataclass


@dataclass(frozen=True)
class FootballSyncState:
    status: str

    ALLOWED_STATUSES = frozenset(
        {
            "seen_current_sync",
            "temporarily_missing",
            "confirmed_removed",
        }
    )

    def __post_init__(self):
        normalized_status = self.status.strip().casefold()

        if normalized_status not in self.ALLOWED_STATUSES:
            raise ValueError(
                "estado de sincronización de fútbol no permitido"
            )