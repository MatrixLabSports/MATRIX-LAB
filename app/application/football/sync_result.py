from dataclasses import dataclass


@dataclass(frozen=True)
class FootballSyncResult:
    status: str
    received_count: int
    accepted_count: int
    rejected_count: int

    ALLOWED_STATUSES = frozenset(
        {
            "completed",
            "partial",
            "failed",
        }
    )

    def __post_init__(self):
        normalized_status = self.status.strip().casefold()

        if normalized_status not in self.ALLOWED_STATUSES:
            raise ValueError(
                "estado de sincronización de fútbol no permitido"
            )

        counts = (
            self.received_count,
            self.accepted_count,
            self.rejected_count,
        )

        if any(
            not isinstance(count, int) or count < 0
            for count in counts
        ):
            raise ValueError(
                "conteos de sincronización deben ser enteros no negativos"
            )

        if self.accepted_count + self.rejected_count > self.received_count:
            raise ValueError(
                "aceptados y rechazados no pueden superar los recibidos"
            )

        if (
            normalized_status == "completed"
            and self.accepted_count + self.rejected_count
            != self.received_count
        ):
            raise ValueError(
                "sincronización completa debe contabilizar todos los recibidos"
            )

    @property
    def can_reconcile_missing(self) -> bool:
        return self.status.strip().casefold() == "completed"
