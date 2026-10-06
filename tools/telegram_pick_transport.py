from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class TelegramTransportReceipt:
    ok: bool
    message_id: int
    chat_id: str
    message_sha256: str


def send_telegram_message(
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    timeout_seconds: int = 15,
    session: Any = requests,
) -> TelegramTransportReceipt:
    """
    Transport-only Telegram sender.

    This module does not select bets, calculate probabilities,
    derive P_MATRIX from odds, or execute wagers.

    The caller must enforce MATRIX governance before transport.
    """

    if not bot_token or not bot_token.strip():
        raise ValueError("TELEGRAM_BOT_TOKEN_MISSING")

    if not chat_id or not str(chat_id).strip():
        raise ValueError("TELEGRAM_CHAT_ID_MISSING")

    if not text or not text.strip():
        raise ValueError("TELEGRAM_MESSAGE_EMPTY")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "protect_content": True,
        "disable_web_page_preview": True,
    }

    response = session.post(
        url,
        data=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()

    body = response.json()

    if body.get("ok") is not True:
        raise RuntimeError("TELEGRAM_API_NOT_OK")

    result = body.get("result") or {}

    message_id = result.get("message_id")
    if message_id is None:
        raise RuntimeError("TELEGRAM_MESSAGE_ID_MISSING")

    message_sha256 = hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()

    return TelegramTransportReceipt(
        ok=True,
        message_id=int(message_id),
        chat_id=str(chat_id),
        message_sha256=message_sha256,
    )
