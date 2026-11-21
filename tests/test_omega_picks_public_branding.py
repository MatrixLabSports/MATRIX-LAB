from pathlib import Path
from tools.telegram_green_signal_alerts import premium_pick_caption
from tools.matrix_premium_result_watcher import _caption

def test_public_premium_caption_is_omega():
    c={"match":"Equipo A vs Equipo B","market":"Más de 2.5","house":"Betano","odds":1.80}
    out=premium_pick_caption(c)
    assert "OMEGA PICKS PREMIUM" in out
    assert "MATRIX PICKS PREMIUM" not in out

def test_public_result_caption_is_omega():
    rec={"match":"Equipo A vs Equipo B","market":"Más de 2.5","odds":1.80}
    res={"won":True,"home_goals":2,"away_goals":1}
    out=_caption(rec,res)
    assert "OMEGA PICKS PREMIUM" in out
    assert "Resultado registrado por OMEGA PICKS." in out

def test_renderer_source_has_no_public_matrix_brand():
    src=Path("tools/matrix_premium_cards.py").read_text(encoding="utf-8")
    assert "OMEGA PICKS PREMIUM" in src
    assert "RESULTADO REGISTRADO POR OMEGA PICKS" in src
    assert "MATRIX PICKS PREMIUM" not in src
