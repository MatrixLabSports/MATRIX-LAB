import json
from pathlib import Path
from unittest.mock import Mock

from tools.odds_api_net_colombia_catalog_probe import run


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {
            "X-RateLimit-Limit": "60",
            "X-RateLimit-Remaining": "59",
            "X-RateLimit-Bucket": "minute",
        }
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


def _all_target_items(stake_key: str = "stake"):
    return [
        {"bookmaker": "betano", "country_codes": ["CO"]},
        {"bookmaker": "betplay", "country_codes": ["CO"]},
        {"bookmaker": "betsson", "country_codes": ["CO"]},
        {"bookmaker": "bwin", "country_codes": ["CO"]},
        {"bookmaker": "codere", "country_codes": ["CO"]},
        {"bookmaker": "luckia", "country_codes": ["CO"]},
        {"bookmaker": "mryoker", "country_codes": ["CO"]},
        {"bookmaker": "rivalo", "country_codes": ["CO"]},
        {"bookmaker": "rushbet", "country_codes": ["CO"]},
        {"bookmaker": "sportiumco", "country_codes": ["CO"]},
        {"bookmaker": stake_key, "country_codes": ["CO"]},
        {"bookmaker": "wplay", "country_codes": ["CO"]},
        {"bookmaker": "yajuego", "country_codes": ["CO"]},
        {"bookmaker": "zamba", "country_codes": ["CO"]},
    ]


def test_colombia_catalog_requires_rushbet_and_core_books(tmp_path: Path):
    session = Mock()
    session.get.return_value = FakeResponse({
        "items": [
            {"bookmaker": "rushbet", "country_codes": ["CO"]},
            {"bookmaker": "betplay", "country_codes": ["CO"]},
            {"bookmaker": "betano", "country_codes": ["CO"]},
            {"bookmaker": "bwin", "country_codes": ["CO"]},
            {"bookmaker": "wplay", "country_codes": ["CO"]},
        ]
    })
    result = run("secret", tmp_path, session=session)
    assert result["status"] == "PASS"
    assert result["network_calls_performed"] == 1
    assert result["required_presence"] == {
        "rushbet": True,
        "betplay": True,
        "betano": True,
        "bwin": True,
    }
    assert result["all_required_present"] is True
    assert result["portfolio_status"] == "PASS_WITH_BOOKMAKER_GAPS"
    assert result["portfolio_covered_count"] == 5
    assert result["portfolio_target_count"] == 14
    assert result["real_money"] == "BLOCKED"
    assert result["odds_used_to_generate_model_probability"] is False
    assert (tmp_path / "colombia_bookmakers.bin").is_file()
    assert len(result["raw_sha256"]) == 64


def test_full_execution_portfolio_is_detected_individually(tmp_path: Path):
    session = Mock()
    session.get.return_value = FakeResponse({
        "items": _all_target_items() + [
            {"bookmaker": "pinnacle", "country_codes": ["CO"]},
            {"bookmaker": "unibet", "country_codes": ["CO"]},
        ]
    })
    result = run("secret", tmp_path, session=session)
    assert result["status"] == "PASS"
    assert result["portfolio_status"] == "PASS_ALL_EXECUTION_TARGETS_VISIBLE"
    assert result["portfolio_complete"] is True
    assert result["portfolio_covered_count"] == 14
    assert set(result["execution_portfolio"]) == {
        "betano", "betplay", "betsson", "bwin", "codere", "luckia",
        "mryoker", "rivalo", "rushbet", "sportium", "stake", "wplay",
        "yajuego", "zamba",
    }
    assert all(row["present"] for row in result["execution_portfolio"].values())
    assert all(
        row["execution_eligible_from_catalog_alone"] is False
        for row in result["execution_portfolio"].values()
    )
    assert result["reference_or_blocked_books"]["pinnacle"] == {
        "status": "REFERENCE_ONLY_NOT_COLOMBIA_EXECUTION",
        "present": True,
        "execution_eligible": False,
    }
    assert result["reference_or_blocked_books"]["unibet"] == {
        "status": "BLOCKED_PENDING_COLOMBIA_REGULATORY_RECONCILIATION",
        "present": True,
        "execution_eligible": False,
    }


def test_stakeco_alias_counts_as_stake_colombia(tmp_path: Path):
    session = Mock()
    session.get.return_value = FakeResponse({"items": _all_target_items(stake_key="stakeco")})
    result = run("secret", tmp_path, session=session)
    assert result["portfolio_complete"] is True
    assert result["execution_portfolio"]["stake"]["present"] is True
    assert result["execution_portfolio"]["stake"]["detected_provider_key"] == "stakeco"


def test_missing_one_non_core_book_does_not_mislabel_other_books(tmp_path: Path):
    session = Mock()
    items = [x for x in _all_target_items() if x["bookmaker"] != "codere"]
    session.get.return_value = FakeResponse({"items": items})
    result = run("secret", tmp_path, session=session)
    assert result["status"] == "PASS"
    assert result["portfolio_status"] == "PASS_WITH_BOOKMAKER_GAPS"
    assert result["portfolio_covered_count"] == 13
    assert result["execution_portfolio"]["codere"]["present"] is False
    assert result["execution_portfolio"]["betplay"]["present"] is True


def test_missing_rushbet_blocks_provider_gate(tmp_path: Path):
    session = Mock()
    session.get.return_value = FakeResponse({
        "items": [
            {"bookmaker": "betplay", "country_codes": ["CO"]},
            {"bookmaker": "betano", "country_codes": ["CO"]},
            {"bookmaker": "bwin", "country_codes": ["CO"]},
        ]
    })
    result = run("secret", tmp_path, session=session)
    assert result["status"] == "BLOCKED"
    assert result["portfolio_status"] == "BLOCKED_PROVIDER_GATE"
    assert result["required_presence"]["rushbet"] is False


def test_invalid_items_blocks(tmp_path: Path):
    session = Mock()
    session.get.return_value = FakeResponse({"items": {}})
    result = run("secret", tmp_path, session=session)
    assert result["status"] == "BLOCKED"
    assert result["provider_rows"] == 0
    assert result["portfolio_status"] == "BLOCKED_PROVIDER_GATE"
