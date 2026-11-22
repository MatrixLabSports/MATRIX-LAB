from datetime import datetime,timezone
import pytest
from tools.matrix_betplay_readonly_dom_scout import parse_labels,store_readonly

AT=datetime(2026,11,22,22,29,18,tzinfo=timezone.utc)
URL="https://betplay.com.co/apuestas#sports-hub/football"
LABELS=[
"Apuesta sobre Millonarios FC vs Atlético Bucaramanga - Total de goles - Más de 2.5 en 1.86",
"Apuesta sobre América de Cali vs Deportivo Cali - Total de goles - Más de 2.5 en 2.05",
]

def test_two_exact_public_bookmaker_prices_are_read_only():
    r=parse_labels(LABELS,URL,AT)
    assert r["exact_visible_over25_quote_count"]==2
    assert r["quotes"][0]["decimal_price"]==2.05
    assert r["quotes"][1]["decimal_price"]==1.86
    assert all(row["official_p_matrix"] is None for row in r["quotes"])
    assert all(row["event_kickoff_utc"] is None for row in r["quotes"])
    assert r["telegram_signal_authorized"] is False
    assert r["automatic_wagering"] is False

def test_no_ambiguous_identical_match_prices():
    r=parse_labels([LABELS[0],LABELS[0].replace("1.86","1.92")],URL,AT)
    assert r["exact_visible_over25_quote_count"]==0
    assert r["ambiguous_duplicate_event_labels_rejected"]==1

def test_only_exact_fulltime_25_not_15_or_35():
    wrong=[
        LABELS[0].replace("Más de 2.5","Más de 1.5"),
        LABELS[0].replace("Más de 2.5","Más de 3.5"),
        LABELS[0].replace("Total de goles","Goles primera parte"),
        LABELS[0].replace("Apuesta sobre ","Apuesta en vivo sobre "),
    ]
    assert parse_labels(wrong,URL,AT)["exact_visible_over25_quote_count"]==0

def test_bookmaker_domain_must_be_exact():
    with pytest.raises(ValueError,match="QUOTE_SITE_MUST_BE_AUTHORIZED_BETPLAY_DOMAIN"):
        parse_labels(LABELS,"https://betplay.com.co.example.com/apuestas",AT)

def test_bookmaker_quote_must_exceed_150():
    rows=[LABELS[0].replace("1.86","1.50"),LABELS[1].replace("2.05","1.20")]
    assert parse_labels(rows,URL,AT)["exact_visible_over25_quote_count"]==0

def test_reject_unzoned_capture_timestamp():
    with pytest.raises(ValueError,match="QUOTE_CAPTURE_REQUIRES_REAL_UTC"):
        parse_labels(LABELS,URL,AT.replace(tzinfo=None))

def test_immutable_evidence_contains_neither_p_matrix_nor_telegram(tmp_path):
    report=parse_labels(LABELS,URL,AT)
    path=store_readonly(tmp_path,report)
    assert path.is_file()
    assert "2026-11-22" in str(path)
    assert path.read_text(encoding="utf-8").find('"telegram_signal_authorized": false')>=0
    assert store_readonly(tmp_path,report)==path
    with pytest.raises(ValueError,match="UNSAFE_RESEARCH_EVIDENCE"):
        store_readonly(tmp_path,dict(report,telegram_signal_authorized=True))
