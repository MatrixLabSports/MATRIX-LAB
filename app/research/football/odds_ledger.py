from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterable


def _required_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _positive_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return number


def _sha256_hex(name: str, value: object) -> str:
    text = _required_text(name, value).lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{name} must be a SHA-256 hex digest")
    return text


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class FootballOddsQuote:
    provider: str
    provider_event_id: str
    fixture_id: str
    bookmaker: str
    market_key: str
    selection_key: str
    decimal_odds: float
    quoted_at: datetime
    captured_at: datetime
    phase: str
    quote_role: str
    source_payload_sha256: str
    source_reference: str

    def __post_init__(self) -> None:
        for name in (
            "provider",
            "provider_event_id",
            "fixture_id",
            "bookmaker",
            "market_key",
            "selection_key",
            "source_reference",
        ):
            object.__setattr__(self, name, _required_text(name, getattr(self, name)))
        object.__setattr__(self, "decimal_odds", _positive_float("decimal_odds", self.decimal_odds))
        object.__setattr__(self, "quoted_at", _utc(self.quoted_at, name="quoted_at"))
        object.__setattr__(self, "captured_at", _utc(self.captured_at, name="captured_at"))
        if self.captured_at < self.quoted_at:
            raise ValueError("captured_at cannot be before quoted_at")
        phase = _required_text("phase", self.phase).upper()
        if phase not in {"PREMATCH", "LIVE"}:
            raise ValueError("phase must be PREMATCH or LIVE")
        object.__setattr__(self, "phase", phase)
        role = _required_text("quote_role", self.quote_role).upper()
        if role not in {"EXECUTION", "REFERENCE"}:
            raise ValueError("quote_role must be EXECUTION or REFERENCE")
        object.__setattr__(self, "quote_role", role)
        object.__setattr__(
            self,
            "source_payload_sha256",
            _sha256_hex("source_payload_sha256", self.source_payload_sha256),
        )

    def identity(self) -> tuple[str, str, str, str, str, datetime]:
        return (
            self.provider,
            self.provider_event_id,
            self.bookmaker,
            self.market_key,
            self.selection_key,
            self.quoted_at,
        )

    def as_serializable_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["quoted_at"] = self.quoted_at.isoformat()
        data["captured_at"] = self.captured_at.isoformat()
        return data


@dataclass(frozen=True)
class FootballOddsLedgerEntry:
    sequence: int
    previous_entry_sha256: str
    quote: FootballOddsQuote
    entry_sha256: str

    def as_serializable_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "previous_entry_sha256": self.previous_entry_sha256,
            "quote": self.quote.as_serializable_dict(),
            "entry_sha256": self.entry_sha256,
        }


class FootballOddsLedger:
    GENESIS_HASH = "0" * 64

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @staticmethod
    def _entry_hash(sequence: int, previous_hash: str, quote: FootballOddsQuote) -> str:
        payload = {
            "sequence": sequence,
            "previous_entry_sha256": previous_hash,
            "quote": quote.as_serializable_dict(),
        }
        return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def load(self, *, verify: bool = True) -> list[FootballOddsLedgerEntry]:
        if not self.path.exists():
            return []
        entries: list[FootballOddsLedgerEntry] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.strip():
                    continue
                try:
                    raw = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid odds ledger JSON at line {line_number}") from exc
                quote_raw = raw.get("quote")
                if not isinstance(quote_raw, dict):
                    raise ValueError(f"invalid quote at line {line_number}")
                quote = FootballOddsQuote(
                    provider=quote_raw["provider"],
                    provider_event_id=quote_raw["provider_event_id"],
                    fixture_id=quote_raw["fixture_id"],
                    bookmaker=quote_raw["bookmaker"],
                    market_key=quote_raw["market_key"],
                    selection_key=quote_raw["selection_key"],
                    decimal_odds=quote_raw["decimal_odds"],
                    quoted_at=datetime.fromisoformat(quote_raw["quoted_at"]),
                    captured_at=datetime.fromisoformat(quote_raw["captured_at"]),
                    phase=quote_raw["phase"],
                    quote_role=quote_raw["quote_role"],
                    source_payload_sha256=quote_raw["source_payload_sha256"],
                    source_reference=quote_raw["source_reference"],
                )
                entry = FootballOddsLedgerEntry(
                    sequence=int(raw["sequence"]),
                    previous_entry_sha256=_sha256_hex(
                        "previous_entry_sha256", raw["previous_entry_sha256"]
                    ),
                    quote=quote,
                    entry_sha256=_sha256_hex("entry_sha256", raw["entry_sha256"]),
                )
                entries.append(entry)
        if verify:
            self.verify(entries)
        return entries

    def verify(self, entries: Iterable[FootballOddsLedgerEntry] | None = None) -> None:
        records = list(self.load(verify=False) if entries is None else entries)
        expected_previous = self.GENESIS_HASH
        seen_identities: set[tuple[str, str, str, str, str, datetime]] = set()
        for expected_sequence, entry in enumerate(records, start=1):
            if entry.sequence != expected_sequence:
                raise ValueError("odds ledger sequence gap or reorder detected")
            if entry.previous_entry_sha256 != expected_previous:
                raise ValueError("odds ledger hash chain mismatch")
            expected_hash = self._entry_hash(
                entry.sequence,
                entry.previous_entry_sha256,
                entry.quote,
            )
            if entry.entry_sha256 != expected_hash:
                raise ValueError("odds ledger entry hash mismatch")
            identity = entry.quote.identity()
            if identity in seen_identities:
                raise ValueError("duplicate odds quote identity detected")
            seen_identities.add(identity)
            expected_previous = entry.entry_sha256

    def append(self, quote: FootballOddsQuote) -> FootballOddsLedgerEntry:
        entries = self.load(verify=True)
        if any(existing.quote.identity() == quote.identity() for existing in entries):
            raise ValueError("duplicate odds quote identity")
        previous_hash = entries[-1].entry_sha256 if entries else self.GENESIS_HASH
        sequence = len(entries) + 1
        entry_hash = self._entry_hash(sequence, previous_hash, quote)
        entry = FootballOddsLedgerEntry(
            sequence=sequence,
            previous_entry_sha256=previous_hash,
            quote=quote,
            entry_sha256=entry_hash,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = _canonical_json(entry.as_serializable_dict())
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized + "\n")
            handle.flush()
        return entry
