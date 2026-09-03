from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
from typing import Any, Iterator, Mapping

UTC = timezone.utc
_ALLOWED_EVENT_TYPES = {
    "EVENT_REGISTERED",
    "DECISION_FROZEN",
    "CLOSING_ODDS_RECORDED",
    "SETTLEMENT_RECORDED",
    "POST_MORTEM_RECORDED",
}
_ALLOWED_ACTIONS = {"BET", "NO_BET"}
_ALLOWED_RISK = {"OK", "DATA_RISK", "MODEL_RISK", "OOD_RISK", "QUARANTINE"}
_SHA256_HEX = frozenset("0123456789abcdef")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )


def _sha(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _optional_text(name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _text(name, value)


def _utc(value: str, *, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _probability(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return number


def _odds(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("decimal_odds must be numeric")
    number = float(value)
    if not isfinite(number) or number <= 1.0:
        raise ValueError("decimal_odds must be greater than 1")
    return number


def _digest(name: str, value: object) -> str:
    text = _text(name, value).lower()
    if len(text) != 64 or any(ch not in _SHA256_HEX for ch in text):
        raise ValueError(f"{name} must be a valid SHA-256 digest")
    return text


def _digests(name: str, values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)) or not values:
        raise ValueError(f"{name} must contain at least one digest")
    out = tuple(_digest(name, value) for value in values)
    if len(out) != len(set(out)):
        raise ValueError(f"{name} must not contain duplicates")
    return out


@dataclass(frozen=True)
class TennisCanonicalEvent:
    event_id: str
    player1_id: str
    player2_id: str
    competition_id: str
    season_id: str
    round: str
    surface: str
    event_start_utc: str
    registered_at_utc: str
    source_provider: str
    source_reference: str
    canonical_event_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "event_id",
            "player1_id",
            "player2_id",
            "competition_id",
            "season_id",
            "round",
            "surface",
            "source_provider",
            "source_reference",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.player1_id == self.player2_id:
            raise ValueError("players must be different")
        start = _utc(self.event_start_utc, name="event_start_utc")
        registered = _utc(self.registered_at_utc, name="registered_at_utc")
        if registered >= start:
            raise ValueError("canonical event must be registered before event start")
        object.__setattr__(self, "event_start_utc", start.isoformat())
        object.__setattr__(self, "registered_at_utc", registered.isoformat())
        object.__setattr__(
            self,
            "canonical_event_sha256",
            _digest("canonical_event_sha256", self.canonical_event_sha256),
        )



def _decision_identity_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "event_id",
        "player1_id",
        "player2_id",
        "competition_id",
        "season_id",
        "round",
        "surface",
        "market_key",
        "selection_key",
        "line_value",
        "model_version",
        "calibration_version",
        "raw_probability",
        "calibrated_probability",
        "uncertainty_low",
        "uncertainty_high",
        "decision_action",
        "decision_reason_codes",
        "data_cutoff_utc",
        "feature_snapshot_at_utc",
        "decision_at_utc",
        "event_start_utc",
        "odds_snapshot_sha256",
        "odds_observed_at_utc",
        "decimal_odds",
        "odds_source_provider",
        "odds_source_reference",
        "odds_source_authorized",
        "feature_snapshot_sha256",
        "model_input_sha256s",
        "canonical_event_sha256",
        "data_quality_status",
        "model_risk_status",
        "ood_status",
        "overlay_delta",
        "overlay_author",
        "overlay_reason_code",
    )
    payload = {key: values[key] for key in keys}
    # Normalize sequence-bearing fields for deterministic JSON.
    payload["decision_reason_codes"] = list(payload["decision_reason_codes"])
    payload["model_input_sha256s"] = list(payload["model_input_sha256s"])
    return payload


def derive_tennis_decision_id(values: Mapping[str, Any]) -> str:
    return _sha({
        "schema": "matrix.tennis-frozen-decision-id/1",
        "payload": _decision_identity_payload(values),
    })


@dataclass(frozen=True)
class TennisFrozenDecision:
    decision_id: str
    event_id: str
    player1_id: str
    player2_id: str
    competition_id: str
    season_id: str
    round: str
    surface: str
    market_key: str
    selection_key: str
    line_value: float | None
    model_version: str
    calibration_version: str
    raw_probability: float
    calibrated_probability: float
    uncertainty_low: float
    uncertainty_high: float
    decision_action: str
    decision_reason_codes: tuple[str, ...]
    data_cutoff_utc: str
    feature_snapshot_at_utc: str
    decision_at_utc: str
    event_start_utc: str
    odds_snapshot_sha256: str
    odds_observed_at_utc: str
    decimal_odds: float
    odds_source_provider: str
    odds_source_reference: str
    odds_source_authorized: bool
    feature_snapshot_sha256: str
    model_input_sha256s: tuple[str, ...]
    canonical_event_sha256: str
    data_quality_status: str
    model_risk_status: str
    ood_status: str
    overlay_delta: float = 0.0
    overlay_author: str | None = None
    overlay_reason_code: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "event_id",
            "player1_id",
            "player2_id",
            "competition_id",
            "season_id",
            "round",
            "surface",
            "market_key",
            "selection_key",
            "model_version",
            "calibration_version",
            "odds_source_provider",
            "odds_source_reference",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.player1_id == self.player2_id:
            raise ValueError("players must be different")
        action = _text("decision_action", self.decision_action).upper()
        if action not in _ALLOWED_ACTIONS:
            raise ValueError("decision_action must be BET or NO_BET")
        object.__setattr__(self, "decision_action", action)
        if not isinstance(self.decision_reason_codes, (tuple, list)) or not self.decision_reason_codes:
            raise ValueError("decision_reason_codes must be a non-empty sequence")
        reasons = tuple(_text("decision_reason_code", item) for item in self.decision_reason_codes)
        if len(reasons) != len(set(reasons)):
            raise ValueError("decision_reason_codes must not contain duplicates")
        object.__setattr__(self, "decision_reason_codes", reasons)

        raw = _probability("raw_probability", self.raw_probability)
        calibrated = _probability("calibrated_probability", self.calibrated_probability)
        low = _probability("uncertainty_low", self.uncertainty_low)
        high = _probability("uncertainty_high", self.uncertainty_high)
        if not low <= calibrated <= high:
            raise ValueError("calibrated_probability must lie inside uncertainty interval")
        object.__setattr__(self, "raw_probability", raw)
        object.__setattr__(self, "calibrated_probability", calibrated)
        object.__setattr__(self, "uncertainty_low", low)
        object.__setattr__(self, "uncertainty_high", high)

        if self.overlay_delta != 0.0 or self.overlay_author is not None or self.overlay_reason_code is not None:
            raise ValueError("human probability overlay is forbidden in R17")

        for name in ("data_quality_status", "model_risk_status", "ood_status"):
            value = _text(name, getattr(self, name)).upper()
            if value not in _ALLOWED_RISK:
                raise ValueError(f"unsupported {name}")
            object.__setattr__(self, name, value)

        if not isinstance(self.odds_source_authorized, bool):
            raise ValueError("odds_source_authorized must be bool")
        if action == "BET" and not self.odds_source_authorized:
            raise ValueError("BET requires authorized odds source")
        object.__setattr__(self, "decimal_odds", _odds(self.decimal_odds))

        data_cutoff = _utc(self.data_cutoff_utc, name="data_cutoff_utc")
        feature_at = _utc(self.feature_snapshot_at_utc, name="feature_snapshot_at_utc")
        odds_at = _utc(self.odds_observed_at_utc, name="odds_observed_at_utc")
        decision_at = _utc(self.decision_at_utc, name="decision_at_utc")
        start = _utc(self.event_start_utc, name="event_start_utc")
        if data_cutoff > feature_at:
            raise ValueError("data_cutoff_utc cannot be after feature_snapshot_at_utc")
        if feature_at > decision_at:
            raise ValueError("feature_snapshot_at_utc cannot be after decision_at_utc")
        if odds_at > decision_at:
            raise ValueError("odds_observed_at_utc cannot be after decision_at_utc")
        if decision_at >= start:
            raise ValueError("decision must be frozen strictly before event start")

        object.__setattr__(self, "data_cutoff_utc", data_cutoff.isoformat())
        object.__setattr__(self, "feature_snapshot_at_utc", feature_at.isoformat())
        object.__setattr__(self, "odds_observed_at_utc", odds_at.isoformat())
        object.__setattr__(self, "decision_at_utc", decision_at.isoformat())
        object.__setattr__(self, "event_start_utc", start.isoformat())

        object.__setattr__(
            self,
            "odds_snapshot_sha256",
            _digest("odds_snapshot_sha256", self.odds_snapshot_sha256),
        )
        object.__setattr__(
            self,
            "feature_snapshot_sha256",
            _digest("feature_snapshot_sha256", self.feature_snapshot_sha256),
        )
        object.__setattr__(
            self,
            "canonical_event_sha256",
            _digest("canonical_event_sha256", self.canonical_event_sha256),
        )
        object.__setattr__(
            self,
            "model_input_sha256s",
            _digests("model_input_sha256s", self.model_input_sha256s),
        )

        expected_decision_id = derive_tennis_decision_id(asdict(self))
        if self.decision_id != expected_decision_id:
            raise ValueError("decision_id is not the deterministic canonical decision id")

    @classmethod
    def build(cls, **payload: Any) -> "TennisFrozenDecision":
        data = dict(payload)
        data.pop("decision_id", None)
        provisional = dict(data)
        provisional["decision_id"] = "PENDING"
        provisional.setdefault("overlay_delta", 0.0)
        provisional.setdefault("overlay_author", None)
        provisional.setdefault("overlay_reason_code", None)
        # Normalize sequence-bearing fields for deterministic hashing.
        provisional["decision_reason_codes"] = tuple(provisional["decision_reason_codes"])
        provisional["model_input_sha256s"] = tuple(provisional["model_input_sha256s"])
        decision_id = derive_tennis_decision_id(provisional)
        data["decision_id"] = decision_id
        return cls(**data)

    @property
    def theoretical_edge(self) -> float:
        return self.calibrated_probability * self.decimal_odds - 1.0

    def canonical_sha256(self) -> str:
        return _sha(asdict(self))


@dataclass(frozen=True)
class TennisClosingOdds:
    decision_id: str
    event_id: str
    market_key: str
    selection_key: str
    line_value: float | None
    source_provider: str
    source_reference: str
    observed_at_utc: str
    event_start_utc: str
    decimal_odds: float
    source_authorized: bool

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "event_id",
            "market_key",
            "selection_key",
            "source_provider",
            "source_reference",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if not isinstance(self.source_authorized, bool):
            raise ValueError("source_authorized must be bool")
        observed = _utc(self.observed_at_utc, name="observed_at_utc")
        start = _utc(self.event_start_utc, name="event_start_utc")
        if observed >= start:
            raise ValueError("closing odds must be observed before event start")
        object.__setattr__(self, "observed_at_utc", observed.isoformat())
        object.__setattr__(self, "event_start_utc", start.isoformat())
        object.__setattr__(self, "decimal_odds", _odds(self.decimal_odds))


@dataclass(frozen=True)
class TennisSettlement:
    decision_id: str
    event_id: str
    outcome: bool
    settled_at_utc: str
    event_start_utc: str
    result_source_provider: str
    result_source_reference: str
    result_payload_sha256: str
    provider_definition_version: str

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "event_id",
            "result_source_provider",
            "result_source_reference",
            "provider_definition_version",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if not isinstance(self.outcome, bool):
            raise ValueError("outcome must be bool")
        settled = _utc(self.settled_at_utc, name="settled_at_utc")
        start = _utc(self.event_start_utc, name="event_start_utc")
        if settled <= start:
            raise ValueError("settlement must be observed after event start")
        object.__setattr__(self, "settled_at_utc", settled.isoformat())
        object.__setattr__(self, "event_start_utc", start.isoformat())
        object.__setattr__(
            self,
            "result_payload_sha256",
            _digest("result_payload_sha256", self.result_payload_sha256),
        )


@dataclass(frozen=True)
class TennisPostMortem:
    decision_id: str
    event_id: str
    recorded_at_utc: str
    classification: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        for name in ("decision_id", "event_id", "classification"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        recorded = _utc(self.recorded_at_utc, name="recorded_at_utc")
        object.__setattr__(self, "recorded_at_utc", recorded.isoformat())
        object.__setattr__(self, "evidence_sha256", _digest("evidence_sha256", self.evidence_sha256))


@dataclass(frozen=True)
class TennisLedgerEvent:
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
            raise ValueError("unsupported event_type")
        object.__setattr__(self, "event_type", event_type)
        recorded = _utc(self.recorded_at_utc, name="recorded_at_utc")
        object.__setattr__(self, "recorded_at_utc", recorded.isoformat())
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        if self.previous_event_sha256 is not None:
            object.__setattr__(
                self,
                "previous_event_sha256",
                _digest("previous_event_sha256", self.previous_event_sha256),
            )
        object.__setattr__(self, "event_sha256", _digest("event_sha256", self.event_sha256))

    def hash_payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "recorded_at_utc": self.recorded_at_utc,
            "payload": self.payload,
            "previous_event_sha256": self.previous_event_sha256,
        }

    def verify_hash(self) -> bool:
        return _sha(self.hash_payload()) == self.event_sha256

    @classmethod
    def build(
        cls,
        *,
        sequence: int,
        event_type: str,
        recorded_at_utc: str,
        payload: Mapping[str, Any],
        previous_event_sha256: str | None,
    ) -> "TennisLedgerEvent":
        base = {
            "sequence": sequence,
            "event_type": event_type.upper(),
            "recorded_at_utc": _utc(recorded_at_utc, name="recorded_at_utc").isoformat(),
            "payload": dict(payload),
            "previous_event_sha256": previous_event_sha256,
        }
        return cls(**base, event_sha256=_sha(base))


@dataclass(frozen=True)
class TennisLedgerAudit:
    event_count: int
    registered_event_count: int
    decision_count: int
    bet_count: int
    no_bet_count: int
    closing_odds_count: int
    settlement_count: int
    post_mortem_count: int
    hash_chain_verified: bool
    ledger_sha256: str


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
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


class TennisProspectiveEvidenceLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    def _read_events_unlocked(self) -> list[TennisLedgerEvent]:
        if not self.path.exists():
            return []
        events: list[TennisLedgerEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    raise ValueError(f"blank line in tennis prospective ledger at line {line_number}")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON at line {line_number}") from exc
                events.append(TennisLedgerEvent(**payload))
        self._verify_events(events)
        return events

    @staticmethod
    def _verify_events(events: list[TennisLedgerEvent]) -> None:
        previous: str | None = None
        registered: dict[str, TennisCanonicalEvent] = {}
        decisions: dict[str, TennisFrozenDecision] = {}
        natural_keys: set[tuple[str, str, str, str]] = set()
        closings: set[str] = set()
        settlements: set[str] = set()
        post_mortems: set[str] = set()

        for expected_sequence, event in enumerate(events, start=1):
            if event.sequence != expected_sequence:
                raise ValueError("tennis ledger sequence is not contiguous")
            if event.previous_event_sha256 != previous:
                raise ValueError("tennis ledger hash chain is broken")
            if not event.verify_hash():
                raise ValueError("tennis ledger event SHA-256 mismatch")

            if event.event_type == "EVENT_REGISTERED":
                item = TennisCanonicalEvent(**event.payload)
                if item.event_id in registered:
                    raise ValueError("duplicate canonical tennis event")
                registered[item.event_id] = item

            elif event.event_type == "DECISION_FROZEN":
                item = TennisFrozenDecision(**event.payload)
                canonical = registered.get(item.event_id)
                if canonical is None:
                    raise ValueError("decision references unregistered tennis event")
                if item.decision_id in decisions:
                    raise ValueError("duplicate tennis decision_id")
                natural_key = (item.event_id, item.market_key, item.selection_key, item.model_version)
                if natural_key in natural_keys:
                    raise ValueError("duplicate event-market-selection-model tennis decision")
                if (
                    item.player1_id != canonical.player1_id
                    or item.player2_id != canonical.player2_id
                    or item.competition_id != canonical.competition_id
                    or item.season_id != canonical.season_id
                    or item.round != canonical.round
                    or item.surface != canonical.surface
                    or item.event_start_utc != canonical.event_start_utc
                    or item.canonical_event_sha256 != canonical.canonical_event_sha256
                ):
                    raise ValueError("decision identity does not match canonical tennis event")
                decisions[item.decision_id] = item
                natural_keys.add(natural_key)

            elif event.event_type == "CLOSING_ODDS_RECORDED":
                item = TennisClosingOdds(**event.payload)
                decision = decisions.get(item.decision_id)
                if decision is None:
                    raise ValueError("closing odds references unknown tennis decision")
                if item.decision_id in closings:
                    raise ValueError("duplicate closing odds for tennis decision")
                if (
                    item.event_id != decision.event_id
                    or item.market_key != decision.market_key
                    or item.selection_key != decision.selection_key
                    or item.line_value != decision.line_value
                    or item.event_start_utc != decision.event_start_utc
                ):
                    raise ValueError("closing odds identity mismatch")
                if _utc(item.observed_at_utc, name="observed_at_utc") < _utc(
                    decision.decision_at_utc, name="decision_at_utc"
                ):
                    raise ValueError("closing odds cannot precede frozen decision")
                closings.add(item.decision_id)

            elif event.event_type == "SETTLEMENT_RECORDED":
                item = TennisSettlement(**event.payload)
                decision = decisions.get(item.decision_id)
                if decision is None:
                    raise ValueError("settlement references unknown tennis decision")
                if item.decision_id in settlements:
                    raise ValueError("duplicate settlement for tennis decision")
                if item.event_id != decision.event_id or item.event_start_utc != decision.event_start_utc:
                    raise ValueError("settlement identity mismatch")
                settlements.add(item.decision_id)

            else:
                item = TennisPostMortem(**event.payload)
                decision = decisions.get(item.decision_id)
                if decision is None:
                    raise ValueError("post-mortem references unknown tennis decision")
                if item.decision_id in post_mortems:
                    raise ValueError("duplicate post-mortem for tennis decision")
                if item.event_id != decision.event_id:
                    raise ValueError("post-mortem identity mismatch")
                post_mortems.add(item.decision_id)

            previous = event.event_sha256

    def load_events(self) -> tuple[TennisLedgerEvent, ...]:
        with _exclusive_file_lock(self.lock_path):
            return tuple(self._read_events_unlocked())

    def _append_event(
        self,
        *,
        event_type: str,
        recorded_at_utc: str,
        payload: Mapping[str, Any],
    ) -> TennisLedgerEvent:
        with _exclusive_file_lock(self.lock_path):
            events = self._read_events_unlocked()
            event = TennisLedgerEvent.build(
                sequence=len(events) + 1,
                event_type=event_type,
                recorded_at_utc=recorded_at_utc,
                payload=payload,
                previous_event_sha256=events[-1].event_sha256 if events else None,
            )
            self._verify_events([*events, event])
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(_canonical_json(asdict(event)) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return event

    def register_event(self, event: TennisCanonicalEvent) -> TennisLedgerEvent:
        return self._append_event(
            event_type="EVENT_REGISTERED",
            recorded_at_utc=event.registered_at_utc,
            payload=asdict(event),
        )

    def append_decision(self, decision: TennisFrozenDecision) -> TennisLedgerEvent:
        return self._append_event(
            event_type="DECISION_FROZEN",
            recorded_at_utc=decision.decision_at_utc,
            payload=asdict(decision),
        )

    def append_closing_odds(self, closing: TennisClosingOdds) -> TennisLedgerEvent:
        return self._append_event(
            event_type="CLOSING_ODDS_RECORDED",
            recorded_at_utc=closing.observed_at_utc,
            payload=asdict(closing),
        )

    def append_settlement(self, settlement: TennisSettlement) -> TennisLedgerEvent:
        return self._append_event(
            event_type="SETTLEMENT_RECORDED",
            recorded_at_utc=settlement.settled_at_utc,
            payload=asdict(settlement),
        )

    def append_post_mortem(self, item: TennisPostMortem) -> TennisLedgerEvent:
        return self._append_event(
            event_type="POST_MORTEM_RECORDED",
            recorded_at_utc=item.recorded_at_utc,
            payload=asdict(item),
        )

    def audit(self) -> TennisLedgerAudit:
        with _exclusive_file_lock(self.lock_path):
            events = self._read_events_unlocked()
            raw = self.path.read_bytes() if self.path.is_file() else b""

        registered = [e for e in events if e.event_type == "EVENT_REGISTERED"]
        decisions = [
            TennisFrozenDecision(**e.payload)
            for e in events
            if e.event_type == "DECISION_FROZEN"
        ]
        closings = [e for e in events if e.event_type == "CLOSING_ODDS_RECORDED"]
        settlements = [e for e in events if e.event_type == "SETTLEMENT_RECORDED"]
        post_mortems = [e for e in events if e.event_type == "POST_MORTEM_RECORDED"]
        return TennisLedgerAudit(
            event_count=len(events),
            registered_event_count=len(registered),
            decision_count=len(decisions),
            bet_count=sum(1 for d in decisions if d.decision_action == "BET"),
            no_bet_count=sum(1 for d in decisions if d.decision_action == "NO_BET"),
            closing_odds_count=len(closings),
            settlement_count=len(settlements),
            post_mortem_count=len(post_mortems),
            hash_chain_verified=True,
            ledger_sha256=sha256(raw).hexdigest(),
        )
