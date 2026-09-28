from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from app.market.price_execution import (
    BestPriceDecision,
    ModelProbability,
    StakeDecision,
    decision_fingerprint,
)


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class PriceFreeze:
    freeze_id: str
    frozen_at: datetime
    event_start_at: datetime
    mode: str
    decision_sha256: str
    sport: str
    event_id: str
    model_binding: str
    model_probability: float
    bookmaker: str
    provider: str
    provider_event_id: str
    market_key: str
    bet_type: str
    metric: str | None
    period: str
    line: str | float | int | None
    side: str
    selection_key: str
    decimal_odds: float
    quoted_at: datetime
    quote_sha256: str
    implied_probability: float
    expected_value: float
    edge_probability_points: float
    stake_status: str
    bankroll_fraction: float
    stake_amount: float
    real_money_gate_open: bool
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        frozen = _utc(self.frozen_at, "FROZEN_AT")
        start = _utc(self.event_start_at, "EVENT_START_AT")
        quoted = _utc(self.quoted_at, "QUOTED_AT")
        object.__setattr__(self, "frozen_at", frozen)
        object.__setattr__(self, "event_start_at", start)
        object.__setattr__(self, "quoted_at", quoted)
        if self.mode not in {"SHADOW", "CONTROLLED_LIVE"}:
            raise ValueError("FREEZE_MODE_INVALID")
        if frozen >= start or quoted >= start:
            raise ValueError("FREEZE_NOT_PREMATCH")
        if self.mode == "CONTROLLED_LIVE" and not self.real_money_gate_open:
            raise ValueError("REAL_MONEY_GATE_REQUIRED")
        if self.automatic_wagering:
            raise ValueError("AUTOMATIC_WAGERING_FORBIDDEN")


def build_price_freeze(
    probability: ModelProbability,
    price: BestPriceDecision,
    stake: StakeDecision,
    *,
    frozen_at: datetime,
    event_start_at: datetime,
    mode: str,
    real_money_gate_open: bool,
) -> PriceFreeze:
    if price.status != "PRICE_CANDIDATE" or price.quote is None:
        raise ValueError("PRICE_CANDIDATE_REQUIRED")
    quote = price.quote
    if quote.comparison_key != probability.comparison_key:
        raise ValueError("PROBABILITY_QUOTE_CONTRACT_MISMATCH")
    freeze_time = _utc(frozen_at, "FROZEN_AT")
    if probability.generated_at > freeze_time:
        raise ValueError("P_MATRIX_GENERATED_AFTER_FREEZE")
    if quote.captured_at > freeze_time:
        raise ValueError("QUOTE_CAPTURED_AFTER_FREEZE")
    if stake.status == "BET_CANDIDATE" and not real_money_gate_open:
        raise ValueError("BET_CANDIDATE_WITH_REAL_MONEY_BLOCKED")
    if mode == "CONTROLLED_LIVE" and stake.status != "BET_CANDIDATE":
        raise ValueError("CONTROLLED_LIVE_REQUIRES_BET_CANDIDATE")

    decision_sha = decision_fingerprint(probability, price, stake)
    freeze_id = sha256(
        _canonical_json({
            "decision_sha256": decision_sha,
            "frozen_at": freeze_time.isoformat(),
            "event_start_at": _utc(event_start_at, "EVENT_START_AT").isoformat(),
            "mode": mode,
        }).encode("utf-8")
    ).hexdigest()

    return PriceFreeze(
        freeze_id=freeze_id,
        frozen_at=freeze_time,
        event_start_at=event_start_at,
        mode=mode,
        decision_sha256=decision_sha,
        sport=probability.sport,
        event_id=probability.event_id,
        model_binding=probability.model_binding,
        model_probability=probability.probability,
        bookmaker=quote.bookmaker,
        provider=quote.provider,
        provider_event_id=quote.provider_event_id,
        market_key=quote.market_key,
        bet_type=quote.bet_type,
        metric=quote.metric,
        period=quote.period,
        line=quote.line,
        side=quote.side,
        selection_key=quote.selection_key,
        decimal_odds=quote.decimal_odds,
        quoted_at=quote.quoted_at,
        quote_sha256=quote.quote_fingerprint,
        implied_probability=float(price.implied_probability),
        expected_value=float(price.expected_value),
        edge_probability_points=float(price.edge_probability_points),
        stake_status=stake.status,
        bankroll_fraction=stake.bankroll_fraction,
        stake_amount=stake.amount,
        real_money_gate_open=real_money_gate_open,
        automatic_wagering=False,
    )


@dataclass(frozen=True)
class FreezeLedgerEntry:
    sequence: int
    previous_sha256: str
    freeze: PriceFreeze
    entry_sha256: str


class PriceFreezeLedger:
    GENESIS = "0" * 64

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @staticmethod
    def _freeze_dict(freeze: PriceFreeze) -> dict[str, object]:
        data = asdict(freeze)
        for key in ("frozen_at", "event_start_at", "quoted_at"):
            data[key] = getattr(freeze, key).isoformat()
        return data

    @classmethod
    def _hash(cls, sequence: int, previous: str, freeze: PriceFreeze) -> str:
        return sha256(
            _canonical_json({
                "sequence": sequence,
                "previous_sha256": previous,
                "freeze": cls._freeze_dict(freeze),
            }).encode("utf-8")
        ).hexdigest()

    def load(self, verify: bool = True) -> list[FreezeLedgerEntry]:
        if not self.path.exists():
            return []
        rows: list[FreezeLedgerEntry] = []
        for line_number, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            data = json.loads(raw)
            fd = data["freeze"]
            freeze = PriceFreeze(
                **{
                    **fd,
                    "frozen_at": datetime.fromisoformat(fd["frozen_at"]),
                    "event_start_at": datetime.fromisoformat(fd["event_start_at"]),
                    "quoted_at": datetime.fromisoformat(fd["quoted_at"]),
                }
            )
            rows.append(FreezeLedgerEntry(
                sequence=int(data["sequence"]),
                previous_sha256=str(data["previous_sha256"]),
                freeze=freeze,
                entry_sha256=str(data["entry_sha256"]),
            ))
        if verify:
            self.verify(rows)
        return rows

    def verify(self, entries: Iterable[FreezeLedgerEntry] | None = None) -> None:
        rows = list(self.load(False) if entries is None else entries)
        previous = self.GENESIS
        seen: set[str] = set()
        for expected_sequence, row in enumerate(rows, start=1):
            if row.sequence != expected_sequence:
                raise ValueError("FREEZE_LEDGER_SEQUENCE_INVALID")
            if row.previous_sha256 != previous:
                raise ValueError("FREEZE_LEDGER_CHAIN_INVALID")
            expected_hash = self._hash(row.sequence, previous, row.freeze)
            if row.entry_sha256 != expected_hash:
                raise ValueError("FREEZE_LEDGER_HASH_INVALID")
            if row.freeze.freeze_id in seen:
                raise ValueError("FREEZE_LEDGER_DUPLICATE_FREEZE")
            seen.add(row.freeze.freeze_id)
            previous = row.entry_sha256

    def append(self, freeze: PriceFreeze) -> FreezeLedgerEntry:
        rows = self.load(True)
        if any(row.freeze.freeze_id == freeze.freeze_id for row in rows):
            raise ValueError("FREEZE_LEDGER_DUPLICATE_FREEZE")
        previous = rows[-1].entry_sha256 if rows else self.GENESIS
        sequence = len(rows) + 1
        entry_hash = self._hash(sequence, previous, freeze)
        entry = FreezeLedgerEntry(sequence, previous, freeze, entry_hash)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sequence": sequence,
            "previous_sha256": previous,
            "freeze": self._freeze_dict(freeze),
            "entry_sha256": entry_hash,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical_json(payload) + "\n")
        self.verify([*rows, entry])
        return entry
