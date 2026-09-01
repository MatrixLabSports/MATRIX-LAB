from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import log
import os
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Mapping

from app.application.football.analysis_runner import build_football_operational_analysis


_REQUIRED_PROBABILITIES = (
    "home_win",
    "draw",
    "away_win",
    "over_1_5",
    "over_2_5",
    "over_3_5",
    "btts",
)
_ALLOWED_EVENT_TYPES = {"PREDICTION_FROZEN", "OUTCOME_RECORDED"}


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} cannot be empty")
    return text


def _utc(value: str | datetime, *, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _digest(name: str, value: object) -> str:
    text = _text(name, value).lower()
    if len(text) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    try:
        int(text, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be SHA-256 hex") from exc
    return text


def _git_commit(value: object) -> str:
    text = _text("repository_head", value).lower()
    if len(text) not in {40, 64}:
        raise ValueError("repository_head must be a 40- or 64-hex Git object id")
    try:
        int(text, 16)
    except ValueError as exc:
        raise ValueError("repository_head must be a Git hex object id") from exc
    return text


def _probabilities(value: Mapping[str, Any]) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("probabilities must be a mapping")
    out: dict[str, float] = {}
    for key in _REQUIRED_PROBABILITIES:
        raw = value.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"probability {key} must be numeric")
        number = float(raw)
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"probability {key} outside [0,1]")
        out[key] = number
    if abs((out["home_win"] + out["draw"] + out["away_win"]) - 1.0) > 1e-6:
        raise ValueError("1X2 probabilities must sum to one")
    return out


@dataclass(frozen=True)
class FootballShadowPrediction:
    prediction_id: str
    batch_id: str
    benchmark_id: str
    target_key: str
    fixture_id: str
    fixture_kickoff_utc: str
    frozen_at_utc: str
    repository_head: str
    model_version: str
    model_input_sha256: str
    expected_home_goals: float
    expected_away_goals: float
    probabilities: Mapping[str, float]
    source_benchmark_status: str
    supplemental_evidence_used: bool
    source_equivalence_assumed: bool
    analysis_mode: str = "PRE_FREEZE_PROSPECTIVE_SHADOW"
    money_decisions_enabled: bool = False

    def __post_init__(self) -> None:
        for name in (
            "prediction_id",
            "batch_id",
            "benchmark_id",
            "target_key",
            "fixture_id",
            "repository_head",
            "model_version",
            "source_benchmark_status",
            "analysis_mode",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        object.__setattr__(self, "repository_head", _git_commit(self.repository_head))
        object.__setattr__(
            self, "model_input_sha256", _digest("model_input_sha256", self.model_input_sha256)
        )
        kickoff = _utc(self.fixture_kickoff_utc, name="fixture_kickoff_utc")
        frozen = _utc(self.frozen_at_utc, name="frozen_at_utc")
        if frozen >= kickoff:
            raise ValueError("prediction must be frozen strictly before kickoff")
        object.__setattr__(self, "fixture_kickoff_utc", kickoff.isoformat())
        object.__setattr__(self, "frozen_at_utc", frozen.isoformat())
        for name in ("expected_home_goals", "expected_away_goals"):
            raw = getattr(self, name)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or float(raw) < 0:
                raise ValueError(f"{name} must be a non-negative number")
            object.__setattr__(self, name, float(raw))
        object.__setattr__(self, "probabilities", _probabilities(self.probabilities))
        if self.analysis_mode != "PRE_FREEZE_PROSPECTIVE_SHADOW":
            raise ValueError("analysis_mode must remain PRE_FREEZE_PROSPECTIVE_SHADOW")
        if self.money_decisions_enabled is not False:
            raise ValueError("money decisions are forbidden in prospective shadow")
        if not isinstance(self.supplemental_evidence_used, bool):
            raise ValueError("supplemental_evidence_used must be bool")
        if not isinstance(self.source_equivalence_assumed, bool):
            raise ValueError("source_equivalence_assumed must be bool")

    def canonical_sha256(self) -> str:
        return _sha(asdict(self))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FootballShadowPrediction":
        return cls(**dict(payload))


@dataclass(frozen=True)
class FootballShadowOutcome:
    outcome_id: str
    prediction_id: str
    fixture_id: str
    fixture_kickoff_utc: str
    home_goals: int
    away_goals: int
    settled_at_utc: str
    source_provider: str
    source_reference: str
    source_evidence_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "outcome_id",
            "prediction_id",
            "fixture_id",
            "source_provider",
            "source_reference",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        kickoff = _utc(self.fixture_kickoff_utc, name="fixture_kickoff_utc")
        settled = _utc(self.settled_at_utc, name="settled_at_utc")
        if settled <= kickoff:
            raise ValueError("settlement must be observed after kickoff")
        object.__setattr__(self, "fixture_kickoff_utc", kickoff.isoformat())
        object.__setattr__(self, "settled_at_utc", settled.isoformat())
        object.__setattr__(
            self, "source_evidence_sha256", _digest("source_evidence_sha256", self.source_evidence_sha256)
        )
        for name in ("home_goals", "away_goals"):
            raw = getattr(self, name)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FootballShadowOutcome":
        return cls(**dict(payload))


@dataclass(frozen=True)
class FootballShadowEvent:
    sequence: int
    event_type: str
    recorded_at_utc: str
    payload: Mapping[str, Any]
    previous_event_sha256: str | None
    event_sha256: str

    @classmethod
    def build(
        cls,
        *,
        sequence: int,
        event_type: str,
        recorded_at_utc: str,
        payload: Mapping[str, Any],
        previous_event_sha256: str | None,
    ) -> "FootballShadowEvent":
        if event_type not in _ALLOWED_EVENT_TYPES:
            raise ValueError("unsupported shadow event type")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("sequence must be positive integer")
        recorded = _utc(recorded_at_utc, name="recorded_at_utc").isoformat()
        previous = (
            None
            if previous_event_sha256 is None
            else _digest("previous_event_sha256", previous_event_sha256)
        )
        base = {
            "sequence": sequence,
            "event_type": event_type,
            "recorded_at_utc": recorded,
            "payload": dict(payload),
            "previous_event_sha256": previous,
        }
        return cls(event_sha256=_sha(base), **base)

    def verify_hash(self) -> bool:
        base = {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "recorded_at_utc": self.recorded_at_utc,
            "payload": dict(self.payload),
            "previous_event_sha256": self.previous_event_sha256,
        }
        return self.event_sha256 == _sha(base)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FootballShadowEvent":
        return cls(**dict(payload))


@dataclass(frozen=True)
class FootballShadowLedgerAudit:
    event_count: int
    prediction_count: int
    outcome_count: int
    unsettled_count: int
    hash_chain_verified: bool
    ledger_sha256: str


@dataclass(frozen=True)
class FootballShadowPerformance:
    model_version: str
    settled_predictions: int
    multiclass_brier: float | None
    multiclass_log_loss: float | None
    over_1_5_brier: float | None
    over_2_5_brier: float | None
    over_3_5_brier: float | None
    btts_brier: float | None


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class FootballProspectiveShadowLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    def _read_unlocked(self) -> list[FootballShadowEvent]:
        if not self.path.exists():
            return []
        events: list[FootballShadowEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    raise ValueError(f"blank line in shadow ledger at line {line_number}")
                payload = json.loads(raw)
                events.append(FootballShadowEvent.from_mapping(payload))
        self._verify(events)
        return events

    @staticmethod
    def _verify(events: list[FootballShadowEvent]) -> None:
        previous: str | None = None
        predictions: dict[str, FootballShadowPrediction] = {}
        natural_keys: set[tuple[str, str, str]] = set()
        outcomes: set[str] = set()
        for expected, event in enumerate(events, start=1):
            if event.sequence != expected:
                raise ValueError("shadow ledger sequence is not contiguous")
            if event.previous_event_sha256 != previous:
                raise ValueError("shadow ledger hash chain is broken")
            if not event.verify_hash():
                raise ValueError("shadow ledger event hash mismatch")
            if event.event_type == "PREDICTION_FROZEN":
                prediction = FootballShadowPrediction.from_mapping(event.payload)
                natural = (
                    prediction.fixture_id,
                    prediction.model_version,
                    prediction.batch_id,
                )
                if natural in natural_keys:
                    raise ValueError("duplicate fixture-model-batch shadow prediction")
                if prediction.prediction_id in predictions:
                    raise ValueError("duplicate shadow prediction_id")
                predictions[prediction.prediction_id] = prediction
                natural_keys.add(natural)
            else:
                outcome = FootballShadowOutcome.from_mapping(event.payload)
                prediction = predictions.get(outcome.prediction_id)
                if prediction is None:
                    raise ValueError("shadow outcome references unknown prediction")
                if outcome.prediction_id in outcomes:
                    raise ValueError("duplicate shadow outcome")
                if (
                    outcome.fixture_id != prediction.fixture_id
                    or outcome.fixture_kickoff_utc != prediction.fixture_kickoff_utc
                ):
                    raise ValueError("shadow outcome identity mismatch")
                outcomes.add(outcome.prediction_id)
            previous = event.event_sha256

    def _append(self, *, event_type: str, recorded_at_utc: str, payload: Mapping[str, Any]) -> FootballShadowEvent:
        with _exclusive_lock(self.lock_path):
            events = self._read_unlocked()
            event = FootballShadowEvent.build(
                sequence=len(events) + 1,
                event_type=event_type,
                recorded_at_utc=recorded_at_utc,
                payload=payload,
                previous_event_sha256=events[-1].event_sha256 if events else None,
            )
            self._verify([*events, event])
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(_canonical_json(asdict(event)) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return event

    def append_prediction(self, prediction: FootballShadowPrediction) -> FootballShadowEvent:
        return self._append(
            event_type="PREDICTION_FROZEN",
            recorded_at_utc=prediction.frozen_at_utc,
            payload=asdict(prediction),
        )

    def append_outcome(self, outcome: FootballShadowOutcome) -> FootballShadowEvent:
        return self._append(
            event_type="OUTCOME_RECORDED",
            recorded_at_utc=outcome.settled_at_utc,
            payload=asdict(outcome),
        )

    def load_events(self) -> tuple[FootballShadowEvent, ...]:
        with _exclusive_lock(self.lock_path):
            return tuple(self._read_unlocked())

    def audit(self) -> FootballShadowLedgerAudit:
        with _exclusive_lock(self.lock_path):
            events = self._read_unlocked()
            raw = self.path.read_bytes() if self.path.is_file() else b""
        predictions = [e for e in events if e.event_type == "PREDICTION_FROZEN"]
        outcomes = [e for e in events if e.event_type == "OUTCOME_RECORDED"]
        return FootballShadowLedgerAudit(
            event_count=len(events),
            prediction_count=len(predictions),
            outcome_count=len(outcomes),
            unsettled_count=len(predictions) - len(outcomes),
            hash_chain_verified=True,
            ledger_sha256=sha256(raw).hexdigest(),
        )

    def _materialized(self) -> tuple[dict[str, FootballShadowPrediction], dict[str, FootballShadowOutcome]]:
        predictions: dict[str, FootballShadowPrediction] = {}
        outcomes: dict[str, FootballShadowOutcome] = {}
        for event in self.load_events():
            if event.event_type == "PREDICTION_FROZEN":
                item = FootballShadowPrediction.from_mapping(event.payload)
                predictions[item.prediction_id] = item
            else:
                item = FootballShadowOutcome.from_mapping(event.payload)
                outcomes[item.prediction_id] = item
        return predictions, outcomes

    def performance(self, *, model_version: str) -> FootballShadowPerformance:
        model_version = _text("model_version", model_version)
        predictions, outcomes = self._materialized()
        rows = [
            (prediction, outcomes[prediction.prediction_id])
            for prediction in predictions.values()
            if prediction.model_version == model_version
            and prediction.prediction_id in outcomes
        ]
        if not rows:
            return FootballShadowPerformance(
                model_version=model_version,
                settled_predictions=0,
                multiclass_brier=None,
                multiclass_log_loss=None,
                over_1_5_brier=None,
                over_2_5_brier=None,
                over_3_5_brier=None,
                btts_brier=None,
            )

        multi_brier = 0.0
        multi_log = 0.0
        binary_errors: dict[str, float] = {
            "over_1_5": 0.0,
            "over_2_5": 0.0,
            "over_3_5": 0.0,
            "btts": 0.0,
        }
        epsilon = 1e-15
        for prediction, outcome in rows:
            p = prediction.probabilities
            if outcome.home_goals > outcome.away_goals:
                actual = "home_win"
            elif outcome.home_goals == outcome.away_goals:
                actual = "draw"
            else:
                actual = "away_win"
            for key in ("home_win", "draw", "away_win"):
                target = 1.0 if key == actual else 0.0
                multi_brier += (p[key] - target) ** 2
            multi_log += -log(max(epsilon, p[actual]))
            total = outcome.home_goals + outcome.away_goals
            realized = {
                "over_1_5": total >= 2,
                "over_2_5": total >= 3,
                "over_3_5": total >= 4,
                "btts": outcome.home_goals > 0 and outcome.away_goals > 0,
            }
            for key, flag in realized.items():
                binary_errors[key] += (p[key] - float(flag)) ** 2

        count = len(rows)
        return FootballShadowPerformance(
            model_version=model_version,
            settled_predictions=count,
            multiclass_brier=multi_brier / count,
            multiclass_log_loss=multi_log / count,
            over_1_5_brier=binary_errors["over_1_5"] / count,
            over_2_5_brier=binary_errors["over_2_5"] / count,
            over_3_5_brier=binary_errors["over_3_5"] / count,
            btts_brier=binary_errors["btts"] / count,
        )


@dataclass(frozen=True)
class FootballShadowFreezeResult:
    batch_id: str
    benchmark_id: str
    repository_head: str
    prediction_count: int
    ledger_sha256: str
    model_versions: tuple[str, ...]
    money_decisions_enabled: bool = False
    official_paper_trading: bool = False


def freeze_football_operational_analysis(
    benchmark: Mapping[str, Any],
    *,
    supplement: Mapping[str, Any] | None,
    ledger: FootballProspectiveShadowLedger,
    batch_id: str,
    repository_head: str,
    frozen_at_utc: datetime | None = None,
) -> FootballShadowFreezeResult:
    """Run MATRIX's existing football baseline and freeze its probabilities prospectively.

    This is deliberately a PRE-FREEZE research lane. It does not validate odds,
    EV, CLV, model promotion, official paper trading, CONTROLLED_LIVE, or wagering.
    """

    batch_id = _text("batch_id", batch_id)
    repository_head = _git_commit(repository_head)
    now = _utc(frozen_at_utc or datetime.now(timezone.utc), name="frozen_at_utc")
    result = build_football_operational_analysis(benchmark, supplement=supplement)
    if not result.passed:
        raise ValueError("FOOTBALL_OPERATIONAL_ANALYSIS_NOT_READY")

    canonical = {str(row["target_key"]): row for row in result.canonical_inputs}
    predictions: list[FootballShadowPrediction] = []
    for evaluation in result.experimental_evaluations:
        target_key = str(evaluation["target_key"])
        input_row = canonical.get(target_key)
        if input_row is None:
            raise ValueError("canonical input missing for evaluation")
        probabilities = evaluation.get("probabilities")
        if not isinstance(probabilities, Mapping):
            raise ValueError("ready evaluation missing probabilities")
        kickoff = _utc(str(input_row["kickoff_utc"]), name="fixture_kickoff_utc")
        if now >= kickoff:
            raise ValueError(f"PROSPECTIVE_FREEZE_TOO_LATE:{target_key}")
        if evaluation.get("model_status") != "EXPERIMENTAL_NOT_PROMOTED":
            raise ValueError("unexpected model status for prospective shadow")
        model_version = _text("model_version", evaluation.get("model_name"))
        model_input_sha256 = _digest("input_sha256", evaluation.get("input_sha256"))
        seed = {
            "schema": "matrix.football-prospective-shadow-prediction-id/1",
            "batch_id": batch_id,
            "fixture_id": str(evaluation["fixture_id"]),
            "model_version": model_version,
            "model_input_sha256": model_input_sha256,
            "frozen_at_utc": now.isoformat(),
            "repository_head": repository_head,
        }
        prediction = FootballShadowPrediction(
            prediction_id=_sha(seed),
            batch_id=batch_id,
            benchmark_id=result.benchmark_id,
            target_key=target_key,
            fixture_id=str(evaluation["fixture_id"]),
            fixture_kickoff_utc=kickoff.isoformat(),
            frozen_at_utc=now.isoformat(),
            repository_head=repository_head,
            model_version=model_version,
            model_input_sha256=model_input_sha256,
            expected_home_goals=float(evaluation["expected_home_goals"]),
            expected_away_goals=float(evaluation["expected_away_goals"]),
            probabilities=probabilities,
            source_benchmark_status=result.source_benchmark_status,
            supplemental_evidence_used=result.supplemental_evidence_used,
            source_equivalence_assumed=result.source_equivalence_assumed,
        )
        predictions.append(prediction)

    for prediction in predictions:
        ledger.append_prediction(prediction)
    audit = ledger.audit()
    return FootballShadowFreezeResult(
        batch_id=batch_id,
        benchmark_id=result.benchmark_id,
        repository_head=repository_head,
        prediction_count=len(predictions),
        ledger_sha256=audit.ledger_sha256,
        model_versions=tuple(sorted({item.model_version for item in predictions})),
    )
