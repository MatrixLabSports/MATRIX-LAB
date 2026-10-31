from tools.matrix_dixon_coles_full_challenger import _tau,_over25_from_lambdas

def test_tau_only_adjusts_low_scores():
    assert _tau(2,0,1.4,1.1,-0.1)==1.0
    assert _tau(0,0,1.4,1.1,-0.1)!=1.0
    assert _tau(1,1,1.4,1.1,-0.1)!=1.0

def test_over25_depends_on_refit_lambdas_not_tau_directly():
    p1=_over25_from_lambdas(1.4,1.1)
    p2=_over25_from_lambdas(1.4,1.1)
    assert p1==p2
    assert 0<p1<1
