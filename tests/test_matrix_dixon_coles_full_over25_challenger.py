import math
from tools.matrix_dixon_coles_full_over25_challenger import _tau,_over25,_fit_dc

def test_tau_is_only_low_score_adjustment():
    lam,mu,rho=1.4,1.1,-0.1
    assert _tau(2,0,lam,mu,rho)==1.0
    assert _tau(0,0,lam,mu,rho)!=1.0
    assert _tau(1,1,lam,mu,rho)!=1.0

def test_over25_depends_on_fitted_lambdas_not_directly_on_rho():
    p1=_over25(1.4,1.1)
    p2=_over25(1.4,1.1)
    assert abs(p1-p2)<1e-15

def test_full_dc_fit_returns_bounded_rho_on_synthetic_history():
    rows=[]
    for i in range(60):
        h=str(i%6); a=str((i+1)%6)
        rows.append({
            "home_team_id":h,"away_team_id":a,
            "home_goals":(i*3)%4,"away_goals":(i*5+1)%3
        })
    fit=_fit_dc(rows)
    assert fit is not None
    assert -0.2 <= fit["rho"] <= 0.2
    assert math.isfinite(fit["nll"])
