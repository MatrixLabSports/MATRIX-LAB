from pathlib import Path

import pytest

from tools.telegram_destination_seal import (
    load_destination,
    open_destination,
    seal_destination,
    write_destination,
)


def test_destination_roundtrip_without_plaintext_chat_id(tmp_path: Path):
    payload = seal_destination(
        bot_token="123456:ABCDEF",
        chat_id="987654321",
        chat_type="private",
        bot_id=123456,
    )
    assert payload["schema"] == "MATRIX_TELEGRAM_DESTINATION_V1"
    assert payload["chat_id_plaintext_persisted"] is False
    assert payload["real_money"] == "BLOCKED"
    assert payload["automatic_wagering"] is False
    assert "987654321" not in str(payload)

    path = tmp_path / "destination.json"
    write_destination(path, payload)
    stored = path.read_text(encoding="utf-8")
    assert "987654321" not in stored

    loaded, chat_id = load_destination(path, bot_token="123456:ABCDEF")
    assert loaded["chat_type"] == "private"
    assert chat_id == "987654321"


def test_wrong_token_cannot_decrypt_destination():
    payload = seal_destination(
        bot_token="123456:ABCDEF",
        chat_id="987654321",
        chat_type="private",
        bot_id=123456,
    )
    with pytest.raises(ValueError, match="TELEGRAM_DESTINATION_DECRYPT_FAILED"):
        open_destination(payload, bot_token="999999:WRONG")


def test_missing_token_fails_closed():
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN_NOT_CONFIGURED"):
        seal_destination(bot_token="", chat_id="1", chat_type="private", bot_id=1)


def test_invalid_chat_type_fails_closed():
    with pytest.raises(ValueError, match="TELEGRAM_CHAT_TYPE_INVALID"):
        seal_destination(
            bot_token="123456:ABCDEF",
            chat_id="1",
            chat_type="mystery",
            bot_id=1,
        )
