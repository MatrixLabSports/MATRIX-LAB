import pytest

from app.providers.api_football.config import ApiFootballConfig


def test_api_football_config_loads_key_from_environment(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")

    config = ApiFootballConfig.from_environment()

    assert config.api_key == "test-key"
    assert config.base_url == "https://v3.football.api-sports.io"
    assert config.timeout_seconds == 10.0


def test_api_football_config_rejects_missing_key(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    monkeypatch.setattr(
        "app.providers.api_football.config.load_dotenv",
        lambda: None,
    )

    with pytest.raises(
        ValueError,
        match="API_FOOTBALL_KEY no está configurada",
    ):
        ApiFootballConfig.from_environment()