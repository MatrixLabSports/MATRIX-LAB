from pathlib import Path

from app.market.colombia_bookmakers import EXECUTION_BOOKMAKERS
import tools.telegram_green_signal_alerts as alerts
import tools.telegram_quote_attempt_telemetry as telemetry


def test_all_colombia_execution_books_are_in_v3_immutable_telemetry():
    assert telemetry.SCHEMA == "MATRIX_TELEGRAM_QUOTE_ATTEMPT_V3"
    assert set(telemetry.AUTHORIZED) == set(EXECUTION_BOOKMAKERS)
    assert len(telemetry.AUTHORIZED) == 14
    assert set(telemetry.LEGACY_AUTHORIZED) == {"betano", "betplay", "rushbet"}


def test_odds_api_snapshot_request_is_not_hardcoded_to_three_execution_books():
    assert set(alerts.ODDS_API_NET_EXECUTION_BOOKMAKER_KEYS) == {
        alias
        for aliases in EXECUTION_BOOKMAKERS.values()
        for alias in aliases
    }
    assert {"pinnacle", "circa", "fanduel"} <= set(alerts.ODDS_API_NET_SNAPSHOT_BOOKMAKER_KEYS)
    assert {"betano", "betplay", "rushbet", "bwin", "wplay"} <= set(alerts.ODDS_API_NET_SNAPSHOT_BOOKMAKER_KEYS)


def test_telegram_event_discovery_follows_provider_cursor_and_fails_closed_on_cap():
    src = Path("tools/telegram_green_signal_alerts.py").read_text(encoding="utf-8")
    assert 'next_cursor = ep.get("next_cursor")' in src
    assert 'params["cursor"] = cursor' in src
    assert 'BLOCKED_EVENT_SEARCH_PAGINATION_LIMIT' in src
    assert 'event_search_page_count' in src


def test_clv_event_discovery_follows_provider_cursor_and_records_pagination_state():
    src = Path("tools/football_clv_odds_api_net_capture.py").read_text(encoding="utf-8")
    assert 'next_cursor = ep.get("next_cursor")' in src
    assert 'params["cursor"] = cursor' in src
    assert 'event_search_page_count' in src
    assert 'event_search_pagination_blocked' in src


def test_permanent_safety_gates_remain_unchanged():
    assert alerts.SIGNAL_QUALITY_MIN_P_MATRIX == 0.60
    assert alerts.SIGNAL_QUALITY_MIN_REVALIDATED_EV == 0.05
    assert alerts.GREEN_PREMATCH_REVALIDATION_WINDOW_MINUTES == 120
    assert alerts.PAPER_STAKE_MAX_LEVEL == 1
