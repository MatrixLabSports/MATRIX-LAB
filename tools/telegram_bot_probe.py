from __future__ import annotations

import json
from typing import Any, Mapping

import requests

TELEGRAM_API_BASE = "https://api.telegram.org"
TIMEOUT_SECONDS = 15.0


def _token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN_NOT_CONFIGURED")
    token.encode("ascii")
    return token


def probe_bot(
    bot_token: str,
    *,
    session: Any | None = None,
) -> dict[str, Any]:
    token = _token(bot_token)
    client = session or requests.Session()
    response = client.get(
        f"{TELEGRAM_API_BASE}/bot{token}/getMe",
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        raise ValueError("TELEGRAM_GETME_FAILED")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("TELEGRAM_GETME_RESULT_MISSING")
    return {
        "ok": True,
        "bot_id": result.get("id"),
        "username": result.get("username"),
        "first_name": result.get("first_name"),
        "can_join_groups": result.get("can_join_groups"),
        "can_read_all_group_messages": result.get("can_read_all_group_messages"),
        "supports_inline_queries": result.get("supports_inline_queries"),
    }


def discover_chats(
    bot_token: str,
    *,
    session: Any | None = None,
) -> list[dict[str, Any]]:
    token = _token(bot_token)
    client = session or requests.Session()
    response = client.get(
        f"{TELEGRAM_API_BASE}/bot{token}/getUpdates",
        params={"limit": 100, "timeout": 0},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        raise ValueError("TELEGRAM_GETUPDATES_FAILED")
    updates = payload.get("result")
    if not isinstance(updates, list):
        raise ValueError("TELEGRAM_UPDATES_NOT_LIST")

    chats: dict[str, dict[str, Any]] = {}
    for update in updates:
        if not isinstance(update, Mapping):
            continue
        message = (
            update.get("message")
            or update.get("channel_post")
            or update.get("edited_message")
            or update.get("edited_channel_post")
        )
        if not isinstance(message, Mapping):
            continue
        chat = message.get("chat")
        if not isinstance(chat, Mapping) or chat.get("id") is None:
            continue
        chat_id = str(chat["id"])
        chats[chat_id] = {
            "chat_id": chat_id,
            "type": chat.get("type"),
            "title": chat.get("title"),
            "username": chat.get("username"),
            "first_name": chat.get("first_name"),
        }
    return sorted(chats.values(), key=lambda row: row["chat_id"])


def send_connection_test(
    bot_token: str,
    chat_id: str,
    *,
    session: Any | None = None,
) -> dict[str, Any]:
    token = _token(bot_token)
    chat = str(chat_id or "").strip()
    if not chat:
        raise ValueError("TELEGRAM_CHAT_ID_NOT_CONFIGURED")
    client = session or requests.Session()
    response = client.post(
        f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
        json={
            "chat_id": chat,
            "text": (
                "🧪 MATRIX-LAB Telegram conectado\n\n"
                "Estado: PRUEBA / NO APOSTAR\n"
                "REAL_MONEY: BLOCKED\n"
                "Los picks reales solo se enviarán cuando los gates de MATRIX lo permitan."
            ),
            "protect_content": True,
            "disable_web_page_preview": True,
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        raise ValueError("TELEGRAM_TEST_MESSAGE_FAILED")
    result = payload.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("message_id"), int):
        raise ValueError("TELEGRAM_TEST_MESSAGE_ID_MISSING")
    return {
        "ok": True,
        "message_id": int(result["message_id"]),
        "chat_id": chat,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--send-test", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    print(json.dumps({"bot": probe_bot(token)}, ensure_ascii=False, sort_keys=True))

    if args.discover:
        print(json.dumps({"chats": discover_chats(token)}, ensure_ascii=False, sort_keys=True))

    if args.send_test:
        result = send_connection_test(
            token,
            os.environ.get("TELEGRAM_CHAT_ID", ""),
        )
        print(json.dumps({"test": result}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
