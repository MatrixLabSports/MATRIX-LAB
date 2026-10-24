from pathlib import Path

PROBE = Path(".github/workflows/live-tennis-api-tennis-fallback-probe.yml")
NATIVE = Path(".github/workflows/live-tennis-paid-native-lane.yml")
REACTIVATE = Path(".github/workflows/live-tennis-reactivation-cumulative-gates.yml")


def test_retired_api_tennis_probe_is_disabled():
    raw = PROBE.read_text(encoding="utf-8")
    assert "if: ${{ false }}" in raw
    assert "API-Tennis retired" in raw


def test_retired_api_tennis_native_lane_has_no_schedule_and_is_disabled():
    raw = NATIVE.read_text(encoding="utf-8")
    assert "if: ${{ false }}" in raw
    assert "API-Tennis retired" in raw
    assert "53 */2 * * *" not in raw


def test_reactivation_fails_closed_instead_of_using_retired_api_tennis():
    raw = REACTIVATE.read_text(encoding="utf-8")
    assert raw.count("if: ${{ false }} # API-Tennis retired; NO_NETWORK") >= 2
    assert "LIVE_PRIMARY_UNAVAILABLE_API_TENNIS_RETIRED_FAIL_CLOSED" in raw
    assert "NO_CURRENT_LIVE_LEDGER_API_TENNIS_RETIRED_FAIL_CLOSED" in raw
    assert '"status":"RETIRED_NO_NETWORK"' in raw
