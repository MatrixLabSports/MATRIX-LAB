from app.core.governed_acquisition_queue import build_bounded_acquisition_queue

def build_football_acquisition_queue(*, candidates, budgets, queue_limit=100):
    return build_bounded_acquisition_queue(
        sport="football",
        candidates=candidates,
        budgets=budgets,
        queue_limit=queue_limit,
    )
