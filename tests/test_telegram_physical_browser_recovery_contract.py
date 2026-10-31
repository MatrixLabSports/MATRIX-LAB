from tools.telegram_green_signal_alerts import physical_open_bookmaker_names

def test_physical_browser_coverage_is_currently_12():
    names = physical_open_bookmaker_names()
    assert len(names) == 12
    assert "YaJuego" not in names
    assert "Zamba" not in names

def test_known_open_houses_are_present():
    names = set(physical_open_bookmaker_names())
    assert {"Betano","BetPlay","Betsson","bwin","Codere","Luckia","MrYoker","Rivalo","Rushbet","Sportium","Stake","Wplay"} <= names
