from tools.api_football_checkpoint_200 import build_checkpoint
from tools.api_football_prospective_calibration import _record_sha


def _rows(n: int):
    rows=[]
    previous=None
    for i in range(n):
        row={
            "schema":"MATRIX_FOOTBALL_PROSPECTIVE_CALIBRATION_OBSERVATION_V1",
            "fixture_id":str(200000+i),
            "target_key":f"api_football:fixture:{200000+i}",
            "kickoff_utc":"2026-10-01T18:00:00+00:00",
            "freeze_at_utc":"2026-10-01T12:00:00+00:00",
            "settled_at_utc":"2026-10-01T22:00:00+00:00",
            "input_sha256":"a"*64,
            "frozen_challenger_probabilities":{
                "1x2":{"H":0.60,"D":0.20,"A":0.20},
                "over_2_5":0.60,
                "btts_v2":0.60,
            },
            "frozen_poisson_reference":{
                "1x2":{"H":0.50,"D":0.25,"A":0.25},
                "over_2_5":0.55,
                "btts":0.55,
            },
            "outcomes":{"1x2":"H","over_2_5":True,"btts":True},
            "source_terminal_status":"FT",
            "source_settlement_record_sha256":"b"*64,
            "used_for_parameter_tuning":False,
            "parameters_mutated_after_freeze":False,
            "p_matrix_status":"NOT_GENERATED",
            "automatic_wagering":False,
            "real_money":"BLOCKED",
            "previous_record_sha256":previous,
        }
        row["record_sha256"]=_record_sha(row)
        previous=row["record_sha256"]
        rows.append(row)
    return rows


def test_199_is_sealed():
    d=build_checkpoint(_rows(199))
    assert d["status"]=="SEALED_UNTIL_200"
    assert d["remaining"]==1
    assert d["metrics_opened"] is False
    assert d["metrics"] is None
    assert d["stability_100_to_200"] is None


def test_200_opens_exact_prefix_and_preserves_governance():
    d=build_checkpoint(_rows(200))
    assert d["status"]=="OPENED_AT_200"
    assert d["observations_used"]==200
    assert d["metrics_opened"] is True
    assert d["metrics"]["all_three_markets_pass"] is True
    assert len(d["sample_fixture_ids"])==200
    assert d["parameter_tuning_allowed"] is False
    assert d["original_357_holdout_reuse_allowed"] is False
    assert d["p_matrix_status"]=="NOT_GENERATED"
    assert d["real_money"]=="BLOCKED"


def test_201_keeps_exact_same_200_prefix():
    d200=build_checkpoint(_rows(200))
    d201=build_checkpoint(_rows(201))
    assert d201["observations_used"]==200
    assert d201["sample_prefix_sha256"]==d200["sample_prefix_sha256"]
    assert d201["metrics"]==d200["metrics"]


def test_tamper_fails_closed():
    rows=_rows(200)
    rows[20]["fixture_id"]="tampered"
    try:
        build_checkpoint(rows)
    except ValueError as exc:
        assert "SHA_MISMATCH" in str(exc)
    else:
        raise AssertionError("tampered hash chain must fail")
