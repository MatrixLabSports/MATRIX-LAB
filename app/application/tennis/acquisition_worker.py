from app.core.acquisition_worker import execute_acquisition_queue


def execute_tennis_acquisition_queue(
    *,
    queue_manifest,
    fetcher,
    raw_ledger,
    checkpoints,
    limits,
):
    if queue_manifest.get("sport") != "tennis":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    return execute_acquisition_queue(
        queue_manifest=queue_manifest,
        fetcher=fetcher,
        raw_ledger=raw_ledger,
        checkpoints=checkpoints,
        limits=limits,
    )
