from unittest.mock import Mock

from tools.api_football_pro_entitlement_probe import run


def _resp(rows, errors=None):
    response = Mock()
    response.status_code = 200
    payload = {"errors": errors or [], "response": rows}
    raw = __import__("json").dumps(payload).encode()
    response.content = raw
    response.json.return_value = payload
    return response


def test_pro_probe_requires_both_routes_to_pass(tmp_path):
    session = Mock()
    session.get.side_effect = [_resp([{"x": 1}]), _resp([{"x": 2}, {"x": 3}])]

    result = run("ascii-key", tmp_path, session=session)

    assert result["status"] == "PASS"
    assert result["pro_entitlement_verified"] is True
    assert result["network_calls_performed"] == 2
    assert result["season_2026"]["provider_rows"] == 1
    assert result["team_last_20"]["provider_rows"] == 2
    assert result["real_money"] == "BLOCKED"
    assert (tmp_path / "season_2026.bin").exists()
    assert (tmp_path / "team_1_last_20.bin").exists()
    assert (tmp_path / "manifest.json").exists()


def test_pro_probe_blocks_if_one_route_has_provider_error(tmp_path):
    session = Mock()
    session.get.side_effect = [
        _resp([], {"plan": "blocked"}),
        _resp([{"x": 2}]),
    ]

    result = run("ascii-key", tmp_path, session=session)

    assert result["status"] == "BLOCKED"
    assert result["pro_entitlement_verified"] is False
    assert result["season_2026"]["status"] == "BLOCKED"
    assert result["team_last_20"]["status"] == "PASS"
