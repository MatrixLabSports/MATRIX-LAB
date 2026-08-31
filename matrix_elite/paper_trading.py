from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from statistics import mean
from typing import Iterable

from .postmortem import ALLOWED_CAUSES


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_AWARE")
    return value


def _sha(value: str | None, name: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if value is None or len(value) != 64:
        raise ValueError(f"{name}_REQUIRED")
    int(value, 16)
    return value.lower()


def _canonical(obj: object) -> bytes:
    def convert(value):
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        if isinstance(value, tuple):
            return [convert(x) for x in value]
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        return value
    return (json.dumps(convert(asdict(obj)), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


@dataclass(frozen=True)
class ProspectivePaperDecision:
    decision_id: str
    sport: str
    event_id: str
    market_id: str
    selection_id: str
    decided_at: datetime
    event_start_at: datetime
    action: str
    model_version: str
    feature_version: str
    data_snapshot_sha256: str
    identity_manifest_sha256: str
    thesis_sha256: str
    decision_reason: str
    decimal_odds: float | None = None
    price_provider: str | None = None
    odds_snapshot_sha256: str | None = None
    matrix_probability: float | None = None
    fair_market_probability: float | None = None
    expected_value: float | None = None
    stake_units: float = 0.0
    data_quality_gate_passed: bool = True
    calibration_gate_passed: bool = True
    risk_gate_passed: bool = True
    previous_decision_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.sport not in {"football", "tennis"}:
            raise ValueError("SPORT_BOUNDARY_VIOLATION")
        if self.action not in {"PAPER_BET", "NO_BET", "WATCH", "CANDIDATE"}:
            raise ValueError("PAPER_ACTION_INVALID")
        if not all(str(x).strip() for x in (self.decision_id, self.event_id, self.market_id, self.selection_id, self.model_version, self.feature_version, self.decision_reason)):
            raise ValueError("PAPER_DECISION_METADATA_REQUIRED")
        _aware(self.decided_at, "DECIDED_AT"); _aware(self.event_start_at, "EVENT_START_AT")
        if self.decided_at >= self.event_start_at:
            raise ValueError("DECISION_NOT_PRE_EVENT")
        _sha(self.data_snapshot_sha256, "DATA_SNAPSHOT_SHA256")
        _sha(self.identity_manifest_sha256, "IDENTITY_MANIFEST_SHA256")
        _sha(self.thesis_sha256, "THESIS_SHA256")
        _sha(self.previous_decision_sha256, "PREVIOUS_DECISION_SHA256", required=False)
        if self.stake_units < 0:
            raise ValueError("STAKE_UNITS_NEGATIVE")
        if self.action == "PAPER_BET":
            if not all((self.data_quality_gate_passed, self.calibration_gate_passed, self.risk_gate_passed)):
                raise ValueError("PAPER_BET_GATE_FAILURE")
            if self.decimal_odds is None or self.decimal_odds <= 1 or not self.price_provider:
                raise ValueError("PAPER_BET_PRICE_REQUIRED")
            _sha(self.odds_snapshot_sha256, "ODDS_SNAPSHOT_SHA256")
            if self.matrix_probability is None or not 0 <= self.matrix_probability <= 1:
                raise ValueError("PAPER_BET_MODEL_PROBABILITY_REQUIRED")
            if self.fair_market_probability is None or not 0 <= self.fair_market_probability <= 1:
                raise ValueError("PAPER_BET_MARKET_PROBABILITY_REQUIRED")
            if self.expected_value is None or self.expected_value <= 0:
                raise ValueError("PAPER_BET_POSITIVE_EV_REQUIRED")
            if self.stake_units <= 0:
                raise ValueError("PAPER_BET_POSITIVE_STAKE_REQUIRED")
        elif self.stake_units != 0:
            raise ValueError("NON_BET_ACTION_STAKE_MUST_BE_ZERO")

    def sha256(self) -> str:
        return sha256(_canonical(self)).hexdigest()


@dataclass(frozen=True)
class PostEventReview:
    review_id: str
    decision_id: str
    decision_sha256: str
    event_start_at: datetime
    reviewed_at: datetime
    outcome: str
    pnl_units: float
    settlement_evidence_sha256: str
    closing_line_sha256: str
    closing_fair_probability: float
    postmortem_primary_cause: str
    postmortem_evidence: tuple[str, ...]
    previous_review_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.review_id.strip() or not self.decision_id.strip():
            raise ValueError("REVIEW_METADATA_REQUIRED")
        _sha(self.decision_sha256, "DECISION_SHA256")
        _sha(self.settlement_evidence_sha256, "SETTLEMENT_EVIDENCE_SHA256")
        _sha(self.closing_line_sha256, "CLOSING_LINE_SHA256")
        _sha(self.previous_review_sha256, "PREVIOUS_REVIEW_SHA256", required=False)
        _aware(self.event_start_at, "EVENT_START_AT"); _aware(self.reviewed_at, "REVIEWED_AT")
        if self.reviewed_at <= self.event_start_at:
            raise ValueError("POST_EVENT_REVIEW_TOO_EARLY")
        if self.outcome not in {"WIN", "LOSS", "PUSH", "VOID", "NO_BET_OUTCOME", "WATCH_OUTCOME"}:
            raise ValueError("REVIEW_OUTCOME_INVALID")
        if not 0 <= self.closing_fair_probability <= 1:
            raise ValueError("CLOSING_FAIR_PROBABILITY_INVALID")
        if self.postmortem_primary_cause not in ALLOWED_CAUSES:
            raise ValueError("POSTMORTEM_CAUSE_INVALID")
        if self.postmortem_primary_cause == "LEGITIMATE_VARIANCE" and not self.postmortem_evidence:
            raise ValueError("VARIANCE_REQUIRES_EVIDENCE")

    def sha256(self) -> str:
        return sha256(_canonical(self)).hexdigest()


class ProspectivePaperLedger:
    def __init__(self) -> None:
        self._decisions: list[tuple[ProspectivePaperDecision, str]] = []
        self._reviews: list[tuple[PostEventReview, str]] = []
        self._decision_by_id: dict[str, tuple[ProspectivePaperDecision, str]] = {}
        self._reviewed_decision_ids: set[str] = set()

    def append_decision(self, decision: ProspectivePaperDecision) -> str:
        if decision.decision_id in self._decision_by_id:
            raise ValueError("DUPLICATE_DECISION_ID")
        expected = self._decisions[-1][1] if self._decisions else None
        if decision.previous_decision_sha256 != expected:
            raise ValueError("PAPER_DECISION_CHAIN_MISMATCH")
        digest = decision.sha256()
        self._decisions.append((decision, digest))
        self._decision_by_id[decision.decision_id] = (decision, digest)
        return digest

    def append_review(self, review: PostEventReview) -> str:
        entry = self._decision_by_id.get(review.decision_id)
        if entry is None:
            raise ValueError("REVIEW_DECISION_NOT_FOUND")
        decision, digest = entry
        if review.decision_sha256 != digest:
            raise ValueError("REVIEW_DECISION_HASH_MISMATCH")
        if review.event_start_at != decision.event_start_at:
            raise ValueError("REVIEW_EVENT_START_MISMATCH")
        if review.decision_id in self._reviewed_decision_ids:
            raise ValueError("DUPLICATE_DECISION_REVIEW")
        if decision.action == "PAPER_BET" and review.outcome in {"NO_BET_OUTCOME", "WATCH_OUTCOME"}:
            raise ValueError("PAPER_BET_REVIEW_OUTCOME_MISMATCH")
        if decision.action == "NO_BET" and review.outcome != "NO_BET_OUTCOME":
            raise ValueError("NO_BET_REVIEW_OUTCOME_REQUIRED")
        expected = self._reviews[-1][1] if self._reviews else None
        if review.previous_review_sha256 != expected:
            raise ValueError("PAPER_REVIEW_CHAIN_MISMATCH")
        review_digest = review.sha256()
        self._reviews.append((review, review_digest))
        self._reviewed_decision_ids.add(review.decision_id)
        return review_digest

    def completeness_report(self) -> dict[str, int | float | bool]:
        total = len(self._decisions)
        reviewed = len(self._reviewed_decision_ids)
        paper_bets = sum(1 for d, _ in self._decisions if d.action == "PAPER_BET")
        no_bets = sum(1 for d, _ in self._decisions if d.action == "NO_BET")
        unresolved = total - reviewed
        return {
            "decisions_total": total,
            "reviews_total": reviewed,
            "paper_bets": paper_bets,
            "no_bets": no_bets,
            "unresolved": unresolved,
            "review_completion_rate": reviewed / total if total else 0.0,
            "pass": total > 0 and unresolved == 0,
        }

    def performance_report(self) -> dict[str, float | int]:
        reviews = {r.decision_id: r for r, _ in self._reviews}
        bets = [(d, reviews.get(d.decision_id)) for d, _ in self._decisions if d.action == "PAPER_BET"]
        settled = [(d, r) for d, r in bets if r is not None]
        risked = sum(d.stake_units for d, _ in settled)
        pnl = sum(r.pnl_units for _, r in settled)
        clv = [r.closing_fair_probability - (1.0 / d.decimal_odds) for d, r in settled if d.decimal_odds is not None]
        return {
            "paper_bets": len(bets),
            "settled_paper_bets": len(settled),
            "risked_units": risked,
            "pnl_units": pnl,
            "yield": pnl / risked if risked else 0.0,
            "mean_probability_clv": mean(clv) if clv else 0.0,
        }

    @property
    def decision_count(self) -> int:
        return len(self._decisions)

    @property
    def review_count(self) -> int:
        return len(self._reviews)
