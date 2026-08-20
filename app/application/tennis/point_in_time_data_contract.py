from app.core.point_in_time_data_contract import (
    evaluate_point_in_time_record,
)


def evaluate_tennis_point_in_time_record(
    *,
    record,
    as_of,
    identity_registry,
    mapping_ledger,
):
    return evaluate_point_in_time_record(
        record=record,
        as_of=as_of,
        identity_registry=identity_registry,
        mapping_ledger=mapping_ledger,
        expected_sport="tennis",
    )
