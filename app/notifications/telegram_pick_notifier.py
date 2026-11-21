from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


from app.market.colombia_bookmakers import classify_bookmaker

MIN_DECIMAL_ODDS_EXCLUSIVE = 1.50
ALLOWED_SPORTS = {"football", "tennis"}
ALLOWED_MODES = {"SHADOW", "CONTROLLED_LIVE"}


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name}_MUST_BE_DATETIME")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _text(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name}_REQUIRED")
    return text


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TelegramPickCard:
    pick_id: str
    mode: str
    sport: str
    event_id: str
    event_name: str
    market: str
    selection: str
    bookmaker: str
    decimal_odds: float
    p_matrix: float
    implied_probability: float
    expected_value: float
    stake_amount: float
    stake_currency: str
    freeze_at_utc: datetime
    event_start_at_utc: datetime
    calibration_gate_pass: bool
    real_money_gate_open: bool
    automatic_wagering: bool
    odds_used_as_model_input: bool
    model_binding: str
    price_freeze_sha256: str

    def __post_init__(self) -> None:
        for field in (
            "pick_id", "event_id", "event_name", "market", "selection",
            "bookmaker", "stake_currency", "model_binding", "price_freeze_sha256",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field.upper()))
        if self.mode not in ALLOWED_MODES:
            raise ValueError("PICK_MODE_INVALID")
        if self.sport not in ALLOWED_SPORTS:
            raise ValueError("SPORT_INVALID")

        book = classify_bookmaker(self.bookmaker)
        if not book.execution_eligible:
            raise ValueError("BOOKMAKER_NOT_EXECUTION_ELIGIBLE")

        odds = float(self.decimal_odds)
        p = float(self.p_matrix)
        implied = float(self.implied_probability)
        ev = float(self.expected_value)
        stake = float(self.stake_amount)

        if odds <= MIN_DECIMAL_ODDS_EXCLUSIVE:
            raise ValueError("ODDS_NOT_ABOVE_PERMANENT_MINIMUM")
        if not 0.0 < p < 1.0:
            raise ValueError("P_MATRIX_OUT_OF_RANGE")
        if not 0.0 < implied < 1.0:
            raise ValueError("IMPLIED_PROBABILITY_OUT_OF_RANGE")
        if abs(implied - (1.0 / odds)) > 1e-9:
            raise ValueError("IMPLIED_PROBABILITY_MISMATCH")
        if abs(ev - (p * odds - 1.0)) > 1e-9:
            raise ValueError("EXPECTED_VALUE_MISMATCH")
        if ev <= 0:
            raise ValueError("NON_POSITIVE_EXPECTED_VALUE")

        freeze = _utc(self.freeze_at_utc, "FREEZE_AT")
        start = _utc(self.event_start_at_utc, "EVENT_START_AT")
        object.__setattr__(self, "freeze_at_utc", freeze)
        object.__setattr__(self, "event_start_at_utc", start)
        if freeze >= start:
            raise ValueError("PICK_NOT_PREMATCH")

        digest = self.price_freeze_sha256.lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("PRICE_FREEZE_SHA256_INVALID")
        object.__setattr__(self, "price_freeze_sha256", digest)

        if self.automatic_wagering:
            raise ValueError("AUTOMATIC_WAGERING_FORBIDDEN")
        if self.odds_used_as_model_input:
            raise ValueError("ODDS_TO_P_MATRIX_FORBIDDEN")

        if self.mode == "SHADOW":
            if self.real_money_gate_open:
                raise ValueError("SHADOW_REQUIRES_REAL_MONEY_BLOCKED")
            if stake != 0.0:
                raise ValueError("SHADOW_STAKE_MUST_BE_ZERO")
        else:
            if not self.calibration_gate_pass:
                raise ValueError("CONTROLLED_LIVE_REQUIRES_CALIBRATION_PASS")
            if not self.real_money_gate_open:
                raise ValueError("CONTROLLED_LIVE_REQUIRES_REAL_MONEY_OPEN")
            if stake <= 0:
                raise ValueError("CONTROLLED_LIVE_REQUIRES_POSITIVE_STAKE")


@dataclass(frozen=True)
class TelegramDispatchResult:
    message_id: int
    chat_id: str
    pick_id: str
    message_sha256: str


def format_pick_message(card: TelegramPickCard) -> str:
    if card.mode == "SHADOW":
        header = "🧪 MATRIX SHADOW — NO APOSTAR"
        stake = "Stake: 0 (dinero real bloqueado)"
    else:
        header = "✅ MATRIX CONTROLLED LIVE"
        stake = f"Stake: {card.stake_amount:,.0f} {card.stake_currency}"

    edge_pp = (card.p_matrix - card.implied_probability) * 100.0
    return "\n".join([
        header,
        "",
        f"Deporte: {'Fútbol' if card.sport == 'football' else 'Tenis'}",
        f"Evento: {card.event_name}",
        f"Mercado: {card.market}",
        f"Selección: {card.selection}",
        f"Casa: {card.bookmaker}",
        f"Cuota: {card.decimal_odds:.2f}",
        f"Probabilidad MATRIX: {card.p_matrix * 100:.2f}%",
        f"Probabilidad implícita: {card.implied_probability * 100:.2f}%",
        f"Ventaja: {edge_pp:+.2f} pp",
        f"Valor esperado: {card.expected_value * 100:+.2f}%",
        stake,
        f"Freeze UTC: {card.freeze_at_utc.isoformat()}",
        f"Inicio UTC: {card.event_start_at_utc.isoformat()}",
        f"Modelo: {card.model_binding}",
        f"Pick ID: {card.pick_id}",
    ])


class TelegramDispatchLedger:
    GENESIS = "0" * 64

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        prev = self.GENESIS
        seen: set[str] = set()
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            pick_id = str(row.get("pick_id") or "")
            if not pick_id or pick_id in seen:
                raise ValueError("TELEGRAM_LEDGER_DUPLICATE_OR_MISSING_PICK")
            if row.get("previous_record_sha256") != prev:
                raise ValueError("TELEGRAM_LEDGER_CHAIN_BROKEN")
            body = dict(row)
            record_sha = body.pop("record_sha256", None)
            expected = _sha(body)
            if record_sha != expected:
                raise ValueError("TELEGRAM_LEDGER_RECORD_SHA_MISMATCH")
            prev = record_sha
            seen.add(pick_id)
            rows.append(row)
        return rows

    def append(self, card: TelegramPickCard, result: TelegramDispatchResult) -> dict[str, Any]:
        rows = self._load()
        if any(row["pick_id"] == card.pick_id for row in rows):
            raise ValueError("TELEGRAM_PICK_ALREADY_DISPATCHED")
        row = {
            "schema": "MATRIX_TELEGRAM_PICK_DISPATCH_V1",
            "pick_id": card.pick_id,
            "mode": card.mode,
            "sport": card.sport,
            "event_id": card.event_id,
            "bookmaker": card.bookmaker,
            "decimal_odds": card.decimal_odds,
            "message_id": result.message_id,
            "message_sha256": result.message_sha256,
            "price_freeze_sha256": card.price_freeze_sha256,
            "previous_record_sha256": rows[-1]["record_sha256"] if rows else self.GENESIS,
            "automatic_wagering": False,
            "real_money_gate_open": card.real_money_gate_open,
        }
        row["record_sha256"] = _sha(row)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        self._load()
        return row
