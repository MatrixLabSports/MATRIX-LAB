from app.risk.risk_engine import MatrixRiskEngine


def test_low_risk_is_allowed():
    engine = MatrixRiskEngine()

    result = engine.evaluate_risk(
        data_risk=10,
        statistical_risk=20,
        sporting_risk=15,
        market_risk=20,
        operational_risk=10,
    )

    assert result.allowed_to_continue is True

def test_high_risk_is_blocked():
    engine = MatrixRiskEngine()

    result = engine.evaluate_risk(
        data_risk=80,
        statistical_risk=75,
        sporting_risk=85,
        market_risk=70,
        operational_risk=60,
    )

    assert result.allowed_to_continue is False
    assert result.level == "CRÍTICO"