from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterable


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _money(name: str, value: object, *, allow_zero: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0 or (not allow_zero and number <= 0):
        raise ValueError(f"{name} has invalid amount")
    return round(number, 8)


def _required_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _sha256_hex(name: str, value: object) -> str:
    text = _required_text(name, value).lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{name} must be SHA-256 hex")
    return text


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class FootballRiskRuntimeState:
    bankroll: float
    peak_bankroll: float
    day_start_bankroll: float
    business_date: date
    daily_exposure: float = 0.0
    total_open_exposure: float = 0.0
    market_exposure: tuple[tuple[str, float], ...] = ()
    manual_kill_switch_active: bool = False
    consumed_approval_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "bankroll", _money("bankroll", self.bankroll, allow_zero=False))
        object.__setattr__(self, "peak_bankroll", _money("peak_bankroll", self.peak_bankroll, allow_zero=False))
        object.__setattr__(self, "day_start_bankroll", _money("day_start_bankroll", self.day_start_bankroll, allow_zero=False))
        object.__setattr__(self, "daily_exposure", _money("daily_exposure", self.daily_exposure))
        object.__setattr__(self, "total_open_exposure", _money("total_open_exposure", self.total_open_exposure))
        if self.peak_bankroll + 1e-9 < self.bankroll:
            raise ValueError("peak_bankroll cannot be below bankroll")
        if not isinstance(self.business_date, date) or isinstance(self.business_date, datetime):
            raise TypeError("business_date must be date")
        if not isinstance(self.manual_kill_switch_active, bool):
            raise TypeError("manual_kill_switch_active must be bool")
        if not isinstance(self.consumed_approval_ids, frozenset):
            raise TypeError("consumed_approval_ids must be frozenset")
        normalized_market: list[tuple[str, float]] = []
        seen: set[str] = set()
        for market, amount in self.market_exposure:
            key = _required_text("market", market)
            if key in seen:
                raise ValueError("duplicate market exposure")
            seen.add(key)
            normalized_market.append((key, _money("market exposure", amount)))
        object.__setattr__(self, "market_exposure", tuple(sorted(normalized_market)))
        for approval_id in self.consumed_approval_ids:
            _required_text("approval_id", approval_id)

    def market_amount(self, market_key: str) -> float:
        key = _required_text("market_key", market_key)
        return dict(self.market_exposure).get(key, 0.0)


@dataclass(frozen=True)
class FootballRiskStateEvent:
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", _required_text("event_type", self.event_type).upper())
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at, name="occurred_at"))
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be dict")


@dataclass(frozen=True)
class FootballRiskStateLedgerEntry:
    sequence: int
    previous_entry_sha256: str
    event: FootballRiskStateEvent
    entry_sha256: str


class FootballRiskStateLedger:
    GENESIS_HASH = "0" * 64

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @staticmethod
    def _event_dict(event: FootballRiskStateEvent) -> dict[str, Any]:
        return {
            "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": event.payload,
        }

    @classmethod
    def _entry_hash(cls, sequence: int, previous_hash: str, event: FootballRiskStateEvent) -> str:
        payload = {
            "sequence": sequence,
            "previous_entry_sha256": previous_hash,
            "event": cls._event_dict(event),
        }
        return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def load(self, *, verify: bool = True) -> list[FootballRiskStateLedgerEntry]:
        if not self.path.exists():
            return []
        result: list[FootballRiskStateLedgerEntry] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid risk ledger JSON at line {line_no}") from exc
                event_raw = raw.get("event")
                if not isinstance(event_raw, dict):
                    raise ValueError(f"invalid risk event at line {line_no}")
                event = FootballRiskStateEvent(
                    event_type=event_raw["event_type"],
                    occurred_at=datetime.fromisoformat(event_raw["occurred_at"]),
                    payload=event_raw.get("payload", {}),
                )
                result.append(
                    FootballRiskStateLedgerEntry(
                        sequence=int(raw["sequence"]),
                        previous_entry_sha256=_sha256_hex("previous_entry_sha256", raw["previous_entry_sha256"]),
                        event=event,
                        entry_sha256=_sha256_hex("entry_sha256", raw["entry_sha256"]),
                    )
                )
        if verify:
            self.verify(result)
        return result

    def verify(self, entries: Iterable[FootballRiskStateLedgerEntry] | None = None) -> None:
        records = list(self.load(verify=False) if entries is None else entries)
        previous = self.GENESIS_HASH
        last_time: datetime | None = None
        for expected_sequence, entry in enumerate(records, 1):
            if entry.sequence != expected_sequence:
                raise ValueError("risk ledger sequence gap or reorder detected")
            if entry.previous_entry_sha256 != previous:
                raise ValueError("risk ledger hash chain mismatch")
            expected_hash = self._entry_hash(entry.sequence, previous, entry.event)
            if entry.entry_sha256 != expected_hash:
                raise ValueError("risk ledger entry hash mismatch")
            if last_time is not None and entry.event.occurred_at < last_time:
                raise ValueError("risk ledger event time moved backwards")
            previous = entry.entry_sha256
            last_time = entry.event.occurred_at

    def append(self, event: FootballRiskStateEvent) -> FootballRiskStateLedgerEntry:
        entries = self.load(verify=True)
        if entries and event.occurred_at < entries[-1].event.occurred_at:
            raise ValueError("event time cannot move backwards")
        previous = entries[-1].entry_sha256 if entries else self.GENESIS_HASH
        sequence = len(entries) + 1
        digest = self._entry_hash(sequence, previous, event)
        entry = FootballRiskStateLedgerEntry(sequence, previous, event, digest)
        data = {
            "sequence": sequence,
            "previous_entry_sha256": previous,
            "event": self._event_dict(event),
            "entry_sha256": digest,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical_json(data) + "\n")
            handle.flush()
        return entry

    def rebuild_state(self) -> FootballRiskRuntimeState:
        entries = self.load(verify=True)
        if not entries:
            raise ValueError("risk runtime state has not been initialized")
        state: FootballRiskRuntimeState | None = None
        for entry in entries:
            state = apply_risk_state_event(state, entry.event)
        assert state is not None
        return state


def apply_risk_state_event(
    state: FootballRiskRuntimeState | None,
    event: FootballRiskStateEvent,
) -> FootballRiskRuntimeState:
    kind = event.event_type
    p = event.payload
    if kind == "INITIALIZED":
        if state is not None:
            raise ValueError("risk runtime state already initialized")
        bankroll = _money("bankroll", p["bankroll"], allow_zero=False)
        business_date = date.fromisoformat(_required_text("business_date", p["business_date"]))
        return FootballRiskRuntimeState(
            bankroll=bankroll,
            peak_bankroll=bankroll,
            day_start_bankroll=bankroll,
            business_date=business_date,
        )
    if state is None:
        raise ValueError("first risk state event must be INITIALIZED")

    market_map = dict(state.market_exposure)
    approvals = set(state.consumed_approval_ids)
    bankroll = state.bankroll
    peak = state.peak_bankroll
    day_start = state.day_start_bankroll
    business_date = state.business_date
    daily = state.daily_exposure
    total = state.total_open_exposure
    kill = state.manual_kill_switch_active

    if kind == "DAY_ROLLOVER":
        new_date = date.fromisoformat(_required_text("business_date", p["business_date"]))
        if new_date <= business_date:
            raise ValueError("business date must advance")
        if total > 1e-9:
            raise ValueError("cannot roll day with open exposure")
        business_date = new_date
        day_start = bankroll
        daily = 0.0
        market_map = {}
    elif kind == "BANKROLL_MARKED":
        bankroll = _money("bankroll", p["bankroll"], allow_zero=False)
        peak = max(peak, bankroll)
    elif kind == "EXPOSURE_OPENED":
        market = _required_text("market_key", p["market_key"])
        amount = _money("amount", p["amount"], allow_zero=False)
        daily += amount
        total += amount
        market_map[market] = market_map.get(market, 0.0) + amount
    elif kind == "EXPOSURE_SETTLED":
        market = _required_text("market_key", p["market_key"])
        amount = _money("amount", p["amount"], allow_zero=False)
        existing = market_map.get(market, 0.0)
        if amount > existing + 1e-9 or amount > total + 1e-9:
            raise ValueError("cannot settle more exposure than is open")
        total -= amount
        remaining = existing - amount
        if remaining <= 1e-9:
            market_map.pop(market, None)
        else:
            market_map[market] = remaining
    elif kind == "KILL_SWITCH_SET":
        active = p.get("active")
        if not isinstance(active, bool):
            raise TypeError("kill switch active must be bool")
        kill = active
    elif kind == "APPROVAL_CONSUMED":
        approval_id = _required_text("approval_id", p["approval_id"])
        if approval_id in approvals:
            raise ValueError("approval already consumed")
        approvals.add(approval_id)
    else:
        raise ValueError(f"unsupported risk state event: {kind}")

    return FootballRiskRuntimeState(
        bankroll=bankroll,
        peak_bankroll=peak,
        day_start_bankroll=day_start,
        business_date=business_date,
        daily_exposure=daily,
        total_open_exposure=total,
        market_exposure=tuple(market_map.items()),
        manual_kill_switch_active=kill,
        consumed_approval_ids=frozenset(approvals),
    )
