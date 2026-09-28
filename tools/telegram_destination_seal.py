from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.fernet import Fernet, InvalidToken


def _token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN_NOT_CONFIGURED")
    token.encode("ascii")
    return token


def _key(bot_token: str) -> bytes:
    digest = hashlib.sha256(_token(bot_token).encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest)


def seal_destination(
    *,
    bot_token: str,
    chat_id: str,
    chat_type: str,
    bot_id: int | str,
) -> dict[str, Any]:
    chat = str(chat_id or "").strip()
    if not chat:
        raise ValueError("TELEGRAM_CHAT_ID_REQUIRED")
    ctype = str(chat_type or "").strip().casefold()
    if ctype not in {"private", "group", "supergroup", "channel"}:
        raise ValueError("TELEGRAM_CHAT_TYPE_INVALID")
    cipher = Fernet(_key(bot_token))
    encrypted = cipher.encrypt(chat.encode("utf-8")).decode("ascii")
    return {
        "schema": "MATRIX_TELEGRAM_DESTINATION_V1",
        "sealed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "bot_id": str(bot_id),
        "chat_type": ctype,
        "chat_id_ciphertext": encrypted,
        "chat_id_plaintext_persisted": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def open_destination(payload: Mapping[str, Any], *, bot_token: str) -> str:
    if payload.get("schema") != "MATRIX_TELEGRAM_DESTINATION_V1":
        raise ValueError("TELEGRAM_DESTINATION_SCHEMA_INVALID")
    encrypted = str(payload.get("chat_id_ciphertext") or "").strip()
    if not encrypted:
        raise ValueError("TELEGRAM_DESTINATION_CIPHERTEXT_MISSING")
    try:
        plain = Fernet(_key(bot_token)).decrypt(encrypted.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("TELEGRAM_DESTINATION_DECRYPT_FAILED") from exc
    chat = plain.strip()
    if not chat:
        raise ValueError("TELEGRAM_DESTINATION_EMPTY")
    return chat


def write_destination(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_destination(path: Path, *, bot_token: str) -> tuple[dict[str, Any], str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("TELEGRAM_DESTINATION_ROOT_INVALID")
    return raw, open_destination(raw, bot_token=bot_token)
