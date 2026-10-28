from app.market.colombia_bookmakers import EXECUTION_BOOKMAKERS
from tools.football_daily_governed_over25 import POLICY as DAILY_EV_POLICY
from tools.telegram_green_signal_alerts import POLICY_BOOKS as TELEGRAM_POLICY


def test_colombia_execution_book_catalog_is_single_source_of_truth():
    assert len(EXECUTION_BOOKMAKERS)==14
    assert DAILY_EV_POLICY=={key:list(aliases) for key,aliases in EXECUTION_BOOKMAKERS.items()}
    assert TELEGRAM_POLICY==dict(EXECUTION_BOOKMAKERS)
    assert "pinnacle" not in EXECUTION_BOOKMAKERS


def test_colombia_execution_aliases_cover_human_and_provider_names():
    assert {"mryoker","mr yoker","mr. yoker"} <= set(EXECUTION_BOOKMAKERS["mryoker"])
    assert {"rushbet","rush bet"} <= set(EXECUTION_BOOKMAKERS["rushbet"])
    assert {"sportiumco","sportium"} <= set(EXECUTION_BOOKMAKERS["sportium"])
    assert {"stake","stakeco"} <= set(EXECUTION_BOOKMAKERS["stake"])
    assert {"wplay","w play"} <= set(EXECUTION_BOOKMAKERS["wplay"])
    assert {"yajuego","ya juego"} <= set(EXECUTION_BOOKMAKERS["yajuego"])
