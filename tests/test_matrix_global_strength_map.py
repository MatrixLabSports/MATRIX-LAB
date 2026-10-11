import json
from pathlib import Path

from tools.matrix_global_strength_map import (
    _strength_from_metrics,
    build,
)


def _m(n,db,dl,bci,lci):
    return {
        "n":n,
        "delta_brier":db,
        "delta_log_loss":dl,
        "paired_brier":{"ci95":bci},
        "paired_log_loss":{"ci95":lci},
    }


def test_strong_requires_prospective_sample_and_favorable_uncertainty():
    strength,reason=_strength_from_metrics(_m(40,-0.01,-0.02,[-0.02,-0.001],[-0.04,-0.002]))
    assert strength=="STRONG"
    assert "95CI" in reason


def test_developing_when_signal_not_decisive():
    strength,_=_strength_from_metrics(_m(40,-0.01,-0.02,[-0.02,0.001],[-0.04,0.002]))
    assert strength=="DEVELOPING"


def test_no_go_requires_decisive_underperformance():
    strength,_=_strength_from_metrics(_m(40,0.01,0.02,[0.001,0.02],[0.002,0.04]))
    assert strength=="NO_GO"


def test_insufficient_data_below_tracking_threshold():
    strength,_=_strength_from_metrics(_m(14,-0.1,-0.1,[-0.2,-0.01],[-0.2,-0.01]))
    assert strength=="INSUFFICIENT_DATA"


def test_current_build_is_read_only_and_tennis_metrics_remain_sealed():
    sources=[
        Path("evidence/api_football/prospective_calibration/ledger.jsonl"),
        Path("evidence/api_football/prospective_market_freeze/freeze.json"),
        Path("evidence/cor0203/runtime/MATRIX_COR0203_PHYSICAL_UNIQUENESS_LAST.json"),
        Path("evidence/cor0203/runtime/MATRIX_COR0203_MODEL_BINDING_R707.json"),
    ]
    before={str(p):p.read_bytes() for p in sources}
    payload=build(Path("."))
    after={str(p):p.read_bytes() for p in sources}
    assert before==after

    assert payload["status"]=="PASS"
    assert payload["protections"]["changes_p_matrix"] is False
    assert payload["protections"]["changes_frozen_probabilities"] is False
    assert payload["protections"]["changes_model_parameters"] is False
    assert payload["protections"]["opens_sealed_tennis_metrics"] is False
    assert payload["protections"]["real_money"]=="BLOCKED"

    tennis=[r for r in payload["cells"] if r["sport"]=="TENNIS"]
    assert tennis
    assert all(r["strength_class"]=="INSUFFICIENT_DATA" for r in tennis)
    assert all(r.get("metrics_opened") is False for r in tennis)

    domain=[r for r in tennis if r["scope"]=="DOMAIN"]
    assert len(domain)==1
    uniqueness=json.loads(
        Path(
            "evidence/cor0203/runtime/"
            "MATRIX_COR0203_PHYSICAL_UNIQUENESS_LAST.json"
        ).read_text(encoding="utf-8")
    )
    assert domain[0]["prospective_n"]==uniqueness["unique_calibration_observations"]
    assert domain[0]["remaining_to_600"] == max(
        0,
        600 - uniqueness["unique_calibration_observations"],
    )


def test_current_football_global_markets_include_primary_lanes():
    payload=build(Path("."))
    global_cells={
        r["market"]:r
        for r in payload["cells"]
        if r["sport"]=="FOOTBALL" and r["scope"]=="GLOBAL_MARKET"
    }
    assert "OVER_2_5" in global_cells
    assert "1X2" in global_cells
    assert "BTTS" in global_cells
    assert "PLAYER_SHOTS_V3" in global_cells
    assert global_cells["BTTS"]["strength_class"]=="NO_GO"
    assert global_cells["PLAYER_SHOTS_V3"]["strength_class"]=="DEVELOPING"
