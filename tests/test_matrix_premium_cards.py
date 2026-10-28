from pathlib import Path
from PIL import Image
from tools.matrix_premium_cards import render_pick_png, render_result_png, fingerprint

def candidate():
    return {
        "match":"Equipo Local vs Equipo Visitante",
        "market":"Más de 2.5 goles",
        "house":"Betano",
        "odds":1.82,
        "kickoff_display":"28/10/2026 07:00 PM",
        "paper_bet":{"stake_level":1},
    }

def test_pick_card_png_has_fixed_dimensions_and_forensic_fingerprint(tmp_path):
    p=tmp_path/"pick.png"
    meta=render_pick_png(candidate(),"abc123",p)
    assert p.exists() and p.stat().st_size>10_000
    with Image.open(p) as im:
        assert im.size==(1080,1350)
        assert im.format=="PNG"
    assert meta["fingerprint"]==fingerprint("abc123")

def test_result_cards_render_win_and_loss_without_evaluation_box(tmp_path):
    for won in (True,False):
        p=tmp_path/f"result-{won}.png"
        settlement={"won":won,"home_goals":2,"away_goals":1,"odds":1.82,"market":"Más de 2.5 goles"}
        meta=render_result_png(candidate(),settlement,"abc123",p)
        assert p.exists() and p.stat().st_size>10_000
        assert meta["won"] is won

def test_cards_do_not_expose_internal_committee_or_shadow_labels(tmp_path):
    p=tmp_path/"pick.png"
    render_pick_png(candidate(),"abc123",p)
    raw=p.read_bytes()
    # Metadata-free raster: prohibited internal labels are never embedded as text chunks.
    assert b"comite" not in raw.lower()
    assert b"shadow" not in raw.lower()
    assert b"modo sombra" not in raw.lower()
