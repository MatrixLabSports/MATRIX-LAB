import json
from pathlib import Path

def test_channel_contract():
    cfg=json.loads(Path("config/OMEGA_PICKS_TELEGRAM_CHANNELS.json").read_text(encoding="utf-8"))
    assert cfg["channels"]["FREE"]["visibility"]=="PUBLIC"
    assert cfg["channels"]["PREMIUM"]["visibility"]=="PRIVATE"
    assert cfg["channels"]["STAKAZO_3X"]["visibility"]=="PRIVATE"
    assert cfg["channels"]["FREE"]["name"]=="OMEGA PICKS FREE"
    assert cfg["channels"]["PREMIUM"]["name"]=="OMEGA PICKS PREMIUM"
    assert cfg["channels"]["STAKAZO_3X"]["name"]=="OMEGA PICKS 3X"
    assert cfg["bot"]["external_bots_allowed"] is False
