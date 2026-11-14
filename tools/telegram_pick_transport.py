from __future__ import annotations

from typing import Any, Mapping

import requests

from app.notifications.telegram_pick_notifier import (
    TelegramDispatchResult,
    TelegramPickCard,
    format_pick_message,
)

TELEGRAM_API_BASE = "https://api.telegram.org"


def _text(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name}_REQUIRED")
    return text


def send_pick(
    card: TelegramPickCard,
    *,
    bot_token: str,
    chat_id: str,
    session: Any | None = None,
    timeout_seconds: float = 15.0,
) -> TelegramDispatchResult:
    token = _text(bot_token, "TELEGRAM_BOT_TOKEN")
    chat = _text(chat_id, "TELEGRAM_CHAT_ID")
    token.encode("ascii")

    message = format_pick_message(card)
    client = session or requests.Session()
    response = client.post(
        f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
        json={
            "chat_id": chat,
            "text": message,
            "disable_web_page_preview": True,
            "protect_content": True,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        raise ValueError("TELEGRAM_SEND_FAILED")
    result = payload.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("message_id"), int):
        raise ValueError("TELEGRAM_MESSAGE_ID_MISSING")

    from hashlib import sha256

    return TelegramDispatchResult(
        message_id=int(result["message_id"]),
        chat_id=chat,
        pick_id=card.pick_id,
        message_sha256=sha256(message.encode("utf-8")).hexdigest(),
    )
