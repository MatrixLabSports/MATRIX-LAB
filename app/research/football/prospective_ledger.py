from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from contextlib import contextmanager
from math import isfinite, log
import os
from pathlib import Path
from random import Random
from typing import Any, Iterator, Mapping

from app.research.football.paper_trading import PaperTradeObservation

_ALLOWED_EVENT_TYPES = {
    "DECISION_FROZEN",
    "CLOSING_ODDS_RECORDED",
    "SETTLEMENT_RECORDED",
}
_SHA256_HEX = frozenset("0123456789abcdef")


def _text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _utc(value: str, *, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _probability(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("model_probability must be numeric")
    number = float(value)
    if not isfinite(number) or not 0 <= number <= 1:
        raise ValueError("model_probability must be between 0 and 1")
    return number


def _odds(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("decimal_odds must be numeric")
    number = float(value)
    if not isfinite(number) or number <= 1:
        raise ValueError("decimal_odds must be greater than 1")
    return number


def _digest(value: str, *, name: str) -> str:
    digest = _text(name, value).lower()
    if len(digest) != 64 or any(ch not in _SHA256_HEX for ch in digest):
        raise ValueError(f"{name} must be a valid SHA-256 digest")
    return digest


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("cannot compute quantile of empty values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


@dataclass(frozen=True)
class FrozenProspectiveDecision:
    decision_id: str
    fixture_id: str
    market_key: str
    selection_key: str
    model_version: str
    model_probability: float
    decision_at_utc: str
    fixture_kickoff_utc: str
    block_id: str
    odds_snapshot_sha256: str
    odds_observed_at_utc: str
    decimal_odds: float
    odds_source_provider: str
    odds_source_reference: str
    odds_source_authorized: bool
    model_input_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "fixture_id",
            "market_key",
            "selection_key",
            "model_version",
            "block_id",
            "odds_source_provider",
            "odds_source_reference",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if not isinstance(self.odds_source_authorized, bool):
            raise ValueError("odds_source_authorized must be bool")
        object.__setattr__(self, "model_probability", _probability(self.model_probability))
        object.__setattr__(self, "decimal_odds", _odds(self.decimal_odds))
        object.__setattr__(self, "odds_snapshot_sha256", _digest(self.odds_snapshot_sha256, name="odds_snapshot_sha256"))

        decision_at = _utc(self.decision_at_utc, name="decision_at_utc")
        odds_observed = _utc(self.odds_observed_at_utc, name="odds_observed_at_utc")
        kickoff = _utc(self.fixture_kickoff_utc, name="fixture_kickoff_utc")
        if odds_observed > decision_at:
            raise ValueError("odds_observed_at_utc cannot be after decision_at_utc")
        if decision_at >= kickoff:
            raise ValueError("prospective decision must be frozen strictly before kickoff")
        object.__setattr__(self, "decision_at_utc", decision_at.isoformat())
        object.__setattr__(self, "odds_observed_at_utc", odds_observed.isoformat())
        object.__setattr__(self, "fixture_kickoff_utc", kickoff.isoformat())

        hashes: list[str] = []
        for raw in self.model_input_sha256s:
            hashes.append(_digest(raw, name="model_input_sha256s"))
        if not hashes:
            raise ValueError("model_input_sha256s must contain at least one evidence digest")
        if len(hashes) != len(set(hashes)):
            raise ValueError("model_input_sha256s must not contain duplicates")
        object.__setattr__(self, "model_input_sha256s", tuple(hashes))

    @property
    def theoretical_edge(self) -> float:
        return self.model_probability * self.decimal_odds - 1.0

    def canonical_sha256(self) -> str:
        return _canonical_sha256(asdict(self))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FrozenProspectiveDecision":
        data = dict(payload)
        if isinstance(data.get("model_input_sha256s"), list):
            data["model_input_sha256s"] = tuple(data["model_input_sha256s"])
        return cls(**data)


@dataclass(frozen=True)
class ClosingOddsReference:
    decision_id: str
    fixture_id: str
    market_key: str
    selection_key: str
    source_provider: str
    source_reference: str
    observed_at_utc: str
    fixture_kickoff_utc: str
    decimal_odds: float
    source_authorized: bool

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "fixture_id",
            "market_key",
            "selection_key",
            "source_provider",
            "source_reference",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if not isinstance(self.source_authorized, bool):
            raise ValueError("source_authorized must be bool")
        observed = _utc(self.observed_at_utc, name="observed_at_utc")
        kickoff = _utc(self.fixture_kickoff_utc, name="fixture_kickoff_utc")
        if observed >= kickoff:
            raise ValueError("closing odds reference must still be observed before kickoff")
        object.__setattr__(self, "observed_at_utc", observed.isoformat())
        object.__setattr__(self, "fixture_kickoff_utc", kickoff.isoformat())
        object.__setattr__(self, "decimal_odds", _odds(self.decimal_odds))

    def canonical_sha256(self) -> str:
        return _canonical_sha256(asdict(self))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ClosingOddsReference":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ProspectiveSettlement:
    decision_id: str
    fixture_id: str
    outcome: bool
    settled_at_utc: str
    fixture_kickoff_utc: str
    result_source_provider: str
    result_source_reference: str
    result_payload_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "fixture_id",
            "result_source_provider",
            "result_source_reference",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if not isinstance(self.outcome, bool):
            raise ValueError("outcome must be bool")
        settled = _utc(self.settled_at_utc, name="settled_at_utc")
        kickoff = _utc(self.fixture_kickoff_utc, name="fixture_kickoff_utc")
        if settled <= kickoff:
            raise ValueError("settlement must be observed after kickoff")
        object.__setattr__(self, "settled_at_utc", settled.isoformat())
        object.__setattr__(self, "fixture_kickoff_utc", kickoff.isoformat())
        object.__setattr__(self, "result_payload_sha256", _digest(self.result_payload_sha256, name="result_payload_sha256"))

    def canonical_sha256(self) -> str:
        return _canonical_sha256(asdict(self))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ProspectiveSettlement":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ProspectiveLedgerEvent:
    sequence: int
    event_type: str
    recorded_at_utc: str
    payload: dict[str, Any]
    previous_event_sha256: str | None
    event_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise ValueError("sequence must be a positive integer")
        event_type = _text("event_type", self.event_type).upper()
        if event_type not in _ALLOWED_EVENT_TYPES:
            raise ValueError("unsupported ledger event_type")
        object.__setattr__(self, "event_type", event_type)
        recorded = _utc(self.recorded_at_utc, name="recorded_at_utc")
        object.__setattr__(self, "recorded_at_utc", recorded.isoformat())
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        if self.previous_event_sha256 is not None:
            object.__setattr__(self, "previous_event_sha256", _digest(self.previous_event_sha256, name="previous_event_sha256"))
        object.__setattr__(self, "event_sha256", _digest(self.event_sha256, name="event_sha256"))

    def hash_payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "recorded_at_utc": self.recorded_at_utc,
            "payload": self.payload,
            "previous_event_sha256": self.previous_event_sha256,
        }

    def verify_hash(self) -> bool:
        return _canonical_sha256(self.hash_payload()) == self.event_sha256

    @classmethod
    def build(
        cls,
        *,
        sequence: int,
        event_type: str,
        recorded_at_utc: str,
        payload: Mapping[str, Any],
        previous_event_sha256: str | None,
    ) -> "ProspectiveLedgerEvent":
        base = {
            "sequence": sequence,
            "event_type": event_type.upper(),
            "recorded_at_utc": _utc(recorded_at_utc, name="recorded_at_utc").isoformat(),
            "payload": dict(payload),
            "previous_event_sha256": previous_event_sha256,
        }
        return cls(**base, event_sha256=_canonical_sha256(base))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ProspectiveLedgerEvent":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ProspectiveLedgerAudit:
    event_count: int
    decision_count: int
    closing_odds_count: int
    settlement_count: int
    authorized_entry_odds: bool
    authorized_closing_odds: bool
    timestamp_integrity_verified: bool
    ledger_sha256: str


@dataclass(frozen=True)
class ProspectivePerformanceSummary:
    market_key: str
    model_version: str
    decision_count: int
    closing_odds_count: int
    settled_count: int
    positive_edge_count: int
    mean_theoretical_edge: float
    realized_units: float
    mean_realized_unit_return: float | None
    max_drawdown_units: float
    brier_score: float | None
    calibration_error: float | None
    mean_log_clv: float | None
    mean_log_clv_ci_low: float | None
    mean_log_clv_ci_high: float | None
    max_closing_odds_lead_minutes: float | None
    mean_realized_unit_return_ci_low: float | None
    mean_realized_unit_return_ci_high: float | None


@dataclass(frozen=True)
class ProspectivePerformancePolicy:
    min_settled_samples: int = 450
    min_closing_odds_samples: int = 300
    max_brier_score: float = 0.23
    max_calibration_error: float = 0.06
    require_positive_clv_with_confidence: bool = True
    max_closing_odds_lead_minutes: float = 15.0
    max_mean_unit_loss: float = 0.0

    def __post_init__(self) -> None:
        for name in ("min_settled_samples", "min_closing_odds_samples"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("max_brier_score", "max_calibration_error"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if not isinstance(self.require_positive_clv_with_confidence, bool):
            raise ValueError("require_positive_clv_with_confidence must be bool")
        if isinstance(self.max_closing_odds_lead_minutes, bool) or not isinstance(self.max_closing_odds_lead_minutes, (int, float)) or self.max_closing_odds_lead_minutes <= 0:
            raise ValueError("max_closing_odds_lead_minutes must be positive")
        if isinstance(self.max_mean_unit_loss, bool) or not isinstance(self.max_mean_unit_loss, (int, float)) or self.max_mean_unit_loss < 0:
            raise ValueError("max_mean_unit_loss must be non-negative")

    def reasons_blocked(self, summary: ProspectivePerformanceSummary) -> tuple[str, ...]:
        reasons: list[str] = []
        if summary.settled_count < self.min_settled_samples:
            reasons.append("insufficient_settled_prospective_sample")
        if summary.closing_odds_count < self.min_closing_odds_samples:
            reasons.append("insufficient_closing_odds_sample")
        if (
            summary.max_closing_odds_lead_minutes is None
            or summary.max_closing_odds_lead_minutes > float(self.max_closing_odds_lead_minutes)
        ):
            reasons.append("closing_odds_not_near_kickoff")
        if summary.brier_score is None:
            reasons.append("prospective_brier_missing")
        elif summary.brier_score > self.max_brier_score:
            reasons.append("prospective_brier_above_limit")
        if summary.calibration_error is None:
            reasons.append("prospective_calibration_missing")
        elif summary.calibration_error > self.max_calibration_error:
            reasons.append("prospective_calibration_above_limit")
        if self.require_positive_clv_with_confidence:
            if summary.mean_log_clv_ci_low is None or summary.mean_log_clv_ci_low <= 0:
                reasons.append("positive_clv_not_confirmed")
        elif summary.mean_log_clv is None or summary.mean_log_clv <= 0:
            reasons.append("positive_mean_clv_not_confirmed")
        if summary.mean_realized_unit_return is None:
            reasons.append("prospective_return_missing")
        elif summary.mean_realized_unit_return < -float(self.max_mean_unit_loss):
            reasons.append("prospective_mean_return_below_floor")
        return tuple(dict.fromkeys(reasons))

    def verified(self, summary: ProspectivePerformanceSummary) -> bool:
        return not self.reasons_blocked(summary)


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    """Cross-platform advisory lock used to serialize ledger reads/writes.

    The lock is OS-managed, so an abnormal process exit releases it.  This avoids
    stale lock files while preventing two schedulers from racing the hash chain.
    """

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class FootballProspectiveEvidenceLedger:
    """Append-only, hash-chained prospective evidence ledger.

    This ledger is intentionally local-file based for deterministic research and
    auditability.  It can later be backed by PostgreSQL/event storage without
    changing the event semantics.  Existing events are never edited in-place.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    def _read_events_unlocked(self) -> list[ProspectiveLedgerEvent]:
        if not self.path.exists():
            return []
        events: list[ProspectiveLedgerEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    raise ValueError(f"blank line in prospective ledger at line {line_number}")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON in prospective ledger at line {line_number}") from exc
                events.append(ProspectiveLedgerEvent.from_mapping(payload))
        self._verify_events(events)
        return events

    @staticmethod
    def _verify_events(events: list[ProspectiveLedgerEvent]) -> None:
        previous: str | None = None
        decisions: dict[str, FrozenProspectiveDecision] = {}
        natural_keys: set[tuple[str, str, str, str]] = set()
        closing_seen: set[str] = set()
        settlements_seen: set[str] = set()

        for expected_sequence, event in enumerate(events, start=1):
            if event.sequence != expected_sequence:
                raise ValueError("prospective ledger sequence is not contiguous")
            if event.previous_event_sha256 != previous:
                raise ValueError("prospective ledger hash chain is broken")
            if not event.verify_hash():
                raise ValueError("prospective ledger event SHA-256 mismatch")

            if event.event_type == "DECISION_FROZEN":
                decision = FrozenProspectiveDecision.from_mapping(event.payload)
                if decision.decision_id in decisions:
                    raise ValueError("duplicate prospective decision_id")
                natural_key = (
                    decision.fixture_id,
                    decision.market_key,
                    decision.selection_key,
                    decision.model_version,
                )
                if natural_key in natural_keys:
                    raise ValueError("duplicate fixture-market-selection-model prospective decision")
                decisions[decision.decision_id] = decision
                natural_keys.add(natural_key)
            elif event.event_type == "CLOSING_ODDS_RECORDED":
                closing = ClosingOddsReference.from_mapping(event.payload)
                decision = decisions.get(closing.decision_id)
                if decision is None:
                    raise ValueError("closing odds references unknown decision")
                if closing.decision_id in closing_seen:
                    raise ValueError("duplicate closing odds for decision")
                if (
                    closing.fixture_id != decision.fixture_id
                    or closing.market_key != decision.market_key
                    or closing.selection_key != decision.selection_key
                    or closing.fixture_kickoff_utc != decision.fixture_kickoff_utc
                ):
                    raise ValueError("closing odds identity does not match frozen decision")
                if _utc(closing.observed_at_utc, name="observed_at_utc") < _utc(decision.decision_at_utc, name="decision_at_utc"):
                    raise ValueError("closing odds cannot precede frozen decision")
                closing_seen.add(closing.decision_id)
            else:
                settlement = ProspectiveSettlement.from_mapping(event.payload)
                decision = decisions.get(settlement.decision_id)
                if decision is None:
                    raise ValueError("settlement references unknown decision")
                if settlement.decision_id in settlements_seen:
                    raise ValueError("duplicate settlement for decision")
                if settlement.fixture_id != decision.fixture_id or settlement.fixture_kickoff_utc != decision.fixture_kickoff_utc:
                    raise ValueError("settlement identity does not match frozen decision")
                settlements_seen.add(settlement.decision_id)
            previous = event.event_sha256

    def load_events(self) -> tuple[ProspectiveLedgerEvent, ...]:
        with _exclusive_file_lock(self.lock_path):
            return tuple(self._read_events_unlocked())

    def _append_event(self, *, event_type: str, recorded_at_utc: str, payload: Mapping[str, Any]) -> ProspectiveLedgerEvent:
        with _exclusive_file_lock(self.lock_path):
            events = self._read_events_unlocked()
            previous = events[-1].event_sha256 if events else None
            event = ProspectiveLedgerEvent.build(
                sequence=len(events) + 1,
                event_type=event_type,
                recorded_at_utc=recorded_at_utc,
                payload=payload,
                previous_event_sha256=previous,
            )
            candidate = [*events, event]
            self._verify_events(candidate)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = _canonical_json(asdict(event)) + "\n"
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            return event

    def append_decision(self, decision: FrozenProspectiveDecision) -> ProspectiveLedgerEvent:
        return self._append_event(
            event_type="DECISION_FROZEN",
            recorded_at_utc=decision.decision_at_utc,
            payload=asdict(decision),
        )

    def append_closing_odds(self, closing: ClosingOddsReference) -> ProspectiveLedgerEvent:
        return self._append_event(
            event_type="CLOSING_ODDS_RECORDED",
            recorded_at_utc=closing.observed_at_utc,
            payload=asdict(closing),
        )

    def append_settlement(self, settlement: ProspectiveSettlement) -> ProspectiveLedgerEvent:
        return self._append_event(
            event_type="SETTLEMENT_RECORDED",
            recorded_at_utc=settlement.settled_at_utc,
            payload=asdict(settlement),
        )

    def _file_sha256_unlocked(self) -> str:
        if not self.path.is_file():
            return sha256(b"").hexdigest()
        digest = sha256()
        with self.path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def file_sha256(self) -> str:
        with _exclusive_file_lock(self.lock_path):
            return self._file_sha256_unlocked()

    def audit(self) -> ProspectiveLedgerAudit:
        with _exclusive_file_lock(self.lock_path):
            events = self._read_events_unlocked()
            ledger_sha256 = self._file_sha256_unlocked()
        decisions = [FrozenProspectiveDecision.from_mapping(event.payload) for event in events if event.event_type == "DECISION_FROZEN"]
        closings = [ClosingOddsReference.from_mapping(event.payload) for event in events if event.event_type == "CLOSING_ODDS_RECORDED"]
        settlements = [ProspectiveSettlement.from_mapping(event.payload) for event in events if event.event_type == "SETTLEMENT_RECORDED"]
        return ProspectiveLedgerAudit(
            event_count=len(events),
            decision_count=len(decisions),
            closing_odds_count=len(closings),
            settlement_count=len(settlements),
            authorized_entry_odds=all(item.odds_source_authorized for item in decisions) if decisions else False,
            authorized_closing_odds=all(item.source_authorized for item in closings) if closings else False,
            timestamp_integrity_verified=True,
            ledger_sha256=ledger_sha256,
        )

    def _materialized(self) -> tuple[
        dict[str, FrozenProspectiveDecision],
        dict[str, ClosingOddsReference],
        dict[str, ProspectiveSettlement],
    ]:
        with _exclusive_file_lock(self.lock_path):
            events = self._read_events_unlocked()
        decisions: dict[str, FrozenProspectiveDecision] = {}
        closings: dict[str, ClosingOddsReference] = {}
        settlements: dict[str, ProspectiveSettlement] = {}
        for event in events:
            if event.event_type == "DECISION_FROZEN":
                item = FrozenProspectiveDecision.from_mapping(event.payload)
                decisions[item.decision_id] = item
            elif event.event_type == "CLOSING_ODDS_RECORDED":
                item = ClosingOddsReference.from_mapping(event.payload)
                closings[item.decision_id] = item
            else:
                item = ProspectiveSettlement.from_mapping(event.payload)
                settlements[item.decision_id] = item
        return decisions, closings, settlements

    def paper_observations(self, *, market_key: str, model_version: str) -> tuple[PaperTradeObservation, ...]:
        market_key = _text("market_key", market_key)
        model_version = _text("model_version", model_version)
        decisions, _, settlements = self._materialized()
        rows: list[PaperTradeObservation] = []
        for decision in decisions.values():
            if decision.market_key != market_key or decision.model_version != model_version:
                continue
            settlement = settlements.get(decision.decision_id)
            rows.append(
                PaperTradeObservation(
                    decision_id=decision.decision_id,
                    fixture_id=decision.fixture_id,
                    market_key=decision.market_key,
                    selection_key=decision.selection_key,
                    model_version=decision.model_version,
                    model_probability=decision.model_probability,
                    decision_at_utc=decision.decision_at_utc,
                    odds_snapshot_sha256=decision.odds_snapshot_sha256,
                    decimal_odds=decision.decimal_odds,
                    outcome=None if settlement is None else settlement.outcome,
                    settled_at_utc=None if settlement is None else settlement.settled_at_utc,
                )
            )
        return tuple(rows)

    def performance_summary(
        self,
        *,
        market_key: str,
        model_version: str,
        bootstrap_iterations: int = 2000,
        confidence_level: float = 0.95,
        random_seed: int = 20260730,
        calibration_bins: int = 10,
    ) -> ProspectivePerformanceSummary:
        if isinstance(bootstrap_iterations, bool) or not isinstance(bootstrap_iterations, int) or bootstrap_iterations < 100:
            raise ValueError("bootstrap_iterations must be an integer >= 100")
        if not 0.5 < confidence_level < 1:
            raise ValueError("confidence_level must be between 0.5 and 1")
        if isinstance(calibration_bins, bool) or not isinstance(calibration_bins, int) or calibration_bins < 2:
            raise ValueError("calibration_bins must be an integer >= 2")

        decisions, closings, settlements = self._materialized()
        selected = [
            item for item in decisions.values()
            if item.market_key == market_key and item.model_version == model_version
        ]
        if not selected:
            raise ValueError("prospective performance requires at least one frozen decision")

        settled_rows = [(item, settlements[item.decision_id]) for item in selected if item.decision_id in settlements]
        closing_rows = [(item, closings[item.decision_id]) for item in selected if item.decision_id in closings]
        closing_leads = [
            (
                _utc(closing.fixture_kickoff_utc, name="fixture_kickoff_utc")
                - _utc(closing.observed_at_utc, name="observed_at_utc")
            ).total_seconds() / 60.0
            for _, closing in closing_rows
        ]

        realized_returns: list[float] = []
        running = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for decision, settlement in settled_rows:
            value = decision.decimal_odds - 1.0 if settlement.outcome else -1.0
            realized_returns.append(value)
            running += value
            peak = max(peak, running)
            max_drawdown = max(max_drawdown, peak - running)

        brier: float | None = None
        calibration_error: float | None = None
        if settled_rows:
            brier = sum((decision.model_probability - float(settlement.outcome)) ** 2 for decision, settlement in settled_rows) / len(settled_rows)
            weighted_gap = 0.0
            for index in range(calibration_bins):
                lower = index / calibration_bins
                upper = (index + 1) / calibration_bins
                members = [
                    (decision, settlement)
                    for decision, settlement in settled_rows
                    if lower <= decision.model_probability < upper
                    or (index == calibration_bins - 1 and decision.model_probability == 1.0)
                ]
                if not members:
                    continue
                mean_probability = sum(decision.model_probability for decision, _ in members) / len(members)
                empirical_rate = sum(1.0 if settlement.outcome else 0.0 for _, settlement in members) / len(members)
                weighted_gap += abs(mean_probability - empirical_rate) * len(members) / len(settled_rows)
            calibration_error = weighted_gap

        log_clv_rows = [
            (decision.block_id, log(decision.decimal_odds / closing.decimal_odds))
            for decision, closing in closing_rows
        ]
        mean_log_clv = sum(value for _, value in log_clv_rows) / len(log_clv_rows) if log_clv_rows else None

        clv_ci_low: float | None = None
        clv_ci_high: float | None = None
        return_ci_low: float | None = None
        return_ci_high: float | None = None

        rng = Random(random_seed)
        alpha = (1 - confidence_level) / 2

        def bootstrap_block_means(values: list[tuple[str, float]]) -> tuple[float, float] | None:
            blocks: dict[str, list[float]] = {}
            for block_id, value in values:
                blocks.setdefault(block_id, []).append(value)
            block_ids = sorted(blocks)
            if len(block_ids) < 2:
                return None
            samples: list[float] = []
            for _ in range(bootstrap_iterations):
                sampled_values: list[float] = []
                for _ in block_ids:
                    sampled_values.extend(blocks[rng.choice(block_ids)])
                samples.append(sum(sampled_values) / len(sampled_values))
            samples.sort()
            return _quantile(samples, alpha), _quantile(samples, 1 - alpha)

        clv_ci = bootstrap_block_means(log_clv_rows)
        if clv_ci is not None:
            clv_ci_low, clv_ci_high = clv_ci

        return_block_rows = [
            (
                decision.block_id,
                decision.decimal_odds - 1.0 if settlement.outcome else -1.0,
            )
            for decision, settlement in settled_rows
        ]
        return_ci = bootstrap_block_means(return_block_rows)
        if return_ci is not None:
            return_ci_low, return_ci_high = return_ci

        return ProspectivePerformanceSummary(
            market_key=market_key,
            model_version=model_version,
            decision_count=len(selected),
            closing_odds_count=len(closing_rows),
            settled_count=len(settled_rows),
            positive_edge_count=sum(1 for item in selected if item.theoretical_edge > 0),
            mean_theoretical_edge=sum(item.theoretical_edge for item in selected) / len(selected),
            realized_units=sum(realized_returns),
            mean_realized_unit_return=(sum(realized_returns) / len(realized_returns)) if realized_returns else None,
            max_drawdown_units=max_drawdown,
            brier_score=brier,
            calibration_error=calibration_error,
            mean_log_clv=mean_log_clv,
            mean_log_clv_ci_low=clv_ci_low,
            mean_log_clv_ci_high=clv_ci_high,
            max_closing_odds_lead_minutes=max(closing_leads) if closing_leads else None,
            mean_realized_unit_return_ci_low=return_ci_low,
            mean_realized_unit_return_ci_high=return_ci_high,
        )
