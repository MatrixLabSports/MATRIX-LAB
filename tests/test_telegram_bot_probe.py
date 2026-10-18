from __future__ import annotations

import pytest

from tools.telegram_bot_probe import discover_chats, probe_bot, send_connection_test


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if not 200 <= self.status_code < 300:
            raise RuntimeError("HTTP_ERROR")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.get_calls = []
        self.post_calls = []

    def get(self, url, params=None, timeout=None):
        self.get_calls.append((url, params, timeout))
        if url.endswith("/getMe"):
            return FakeResponse({
                "ok": True,
                "result": {
                    "id": 123,
                    "username": "matrix_test_bot",
                    "first_name": "MATRIX",
                    "can_join_groups": True,
                    "can_read_all_group_messages": False,
                    "supports_inline_queries": False,
                },
            })
        return FakeResponse({
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "chat": {
                            "id": -100123,
                            "type": "supergroup",
                            "title": "MATRIX-LAB PICKS",
                        }
                    },
                },
                {
                    "update_id": 2,
                    "channel_post": {
                        "chat": {
                            "id": -100456,
                            "type": "channel",
                            "title": "MATRIX PICKS CHANNEL",
                        }
                    },
                },
            ],
        })

    def post(self, url, json=None, timeout=None):
        self.post_calls.append((url, json, timeout))
        return FakeResponse({"ok": True, "result": {"message_id": 88}})


def test_probe_bot_returns_identity_without_token_echo():
    s = FakeSession()
    result = probe_bot("123:ABC", session=s)
    assert result["ok"] is True
    assert result["username"] == "matrix_test_bot"
    assert "123:ABC" not in str(result)


def test_discover_chats_returns_only_chat_metadata():
    s = FakeSession()
    rows = discover_chats("123:ABC", session=s)
    assert {r["chat_id"] for r in rows} == {"-100123", "-100456"}
    assert all("text" not in row for row in rows)


def test_send_connection_test_is_shadow_only():
    s = FakeSession()
    result = send_connection_test("123:ABC", "-100123", session=s)
    assert result["ok"] is True
    assert result["message_id"] == 88
    assert result["real_money"] == "BLOCKED"
    assert result["automatic_wagering"] is False
    payload = s.post_calls[0][1]
    assert "NO APOSTAR" in payload["text"]
    assert "REAL_MONEY: BLOCKED" in payload["text"]


def test_missing_token_fails_closed():
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN_NOT_CONFIGURED"):
        probe_bot("")
