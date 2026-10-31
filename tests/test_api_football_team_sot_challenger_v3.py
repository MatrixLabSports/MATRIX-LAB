from tools.api_football_team_sot_challenger_v3 import _calibrate


def test_calibration_shrinks_toward_train_oof_prevalence():
    base=0.5
    assert _calibrate(0.8,base,0.5)==0.65
    assert _calibrate(0.2,base,0.5)==0.35


def test_calibration_never_escapes_probability_bounds():
    assert 0.0 < _calibrate(0.999999,0.5,1.15) < 1.0
    assert 0.0 < _calibrate(0.000001,0.5,1.15) < 1.0
