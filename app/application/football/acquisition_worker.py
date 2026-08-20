from app.core.acquisition_worker import execute_acquisition_queue


def execute_football_acquisition_queue(
    *,
    queue_manifest,
    fetcher,
    raw_ledger,
    checkpoints,
    limits,
    request_budget=None,
):
    if queue_manifest.get("sport") != "football":
        raise ValueError("SPORT_BOUNDARY_VIOLATION")

    return execute_acquisition_queue(
        queue_manifest=queue_manifest,
        fetcher=fetcher,
        raw_ledger=raw_ledger,
        checkpoints=checkpoints,
        limits=limits,
        request_budget=request_budget,
    )
