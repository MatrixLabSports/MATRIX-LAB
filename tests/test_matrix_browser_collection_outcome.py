"""Estados operativos: leer portadas nunca equivale a certificar cuotas."""
from tools.matrix_selfhosted_browser_quote_collector import collection_outcome


def test_no_targets_does_not_pass():
    pages=[{"status":"CAPTURED","bookmaker":"betano"}]
    assert collection_outcome(pages,[],[])=="NO_ELIGIBLE_PREMATCH_TARGETS"


def test_target_without_price_does_not_pass():
    pages=[{"status":"CAPTURED","bookmaker":"betano"}]
    assert collection_outcome(pages,[{"fixture_id":"RESEARCH:1"}],[])=="PREMATCH_TARGETS_WITHOUT_CERTIFIED_EXECUTION_QUOTE"


def test_quote_does_not_authorize_signal():
    pages=[{"status":"CAPTURED","bookmaker":"betano"}]
    result=collection_outcome(pages,[{"fixture_id":"CANONICAL:1"}],[{"price":1.7}])
    assert result=="EXACT_QUOTES_CAPTURED_PENDING_SHARP_MODEL_TELEGRAM_GATES"
    assert result!="TELEGRAM_AUTHORIZED"


def test_no_pages():
    assert collection_outcome([],[],[])=="NO_AUTHORIZED_BOOK_PAGES_VISIBLE"
