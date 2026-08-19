from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable

from app.release.canonical import canonical_sha256
from app.security.provider_reconciliation import ProviderEventSnapshot


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _nonempty(value: str, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} is required")
    return cleaned


def _sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256")


def _nonnegative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


class TruthRevisionKind(str, Enum):
    INITIAL = "INITIAL"
    PROGRESSION = "PROGRESSION"
    CORRECTION = "CORRECTION"
    RETRACTION = "RETRACTION"


class TemporalTruthStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ProviderTruthVersion:
    version_id: str
    provider_id: str
    canonical_fixture_id: str
    provider_fixture_id: str
    snapshot: ProviderEventSnapshot
    known_at: datetime
    valid_from_event_time: datetime
    revision_kind: TruthRevisionKind
    supersedes_version_id: str | None
    correction_scope: tuple[str, ...]
    reason_code: str | None
    evidence_sha256: str
    human_reviewed: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.version_id, "version_id"),
            (self.provider_id, "provider_id"),
            (self.canonical_fixture_id, "canonical_fixture_id"),
            (self.provider_fixture_id, "provider_fixture_id"),
        ):
            _nonempty(value, name)
        _aware(self.known_at, "known_at")
        _aware(self.valid_from_event_time, "valid_from_event_time")
        _sha256(self.evidence_sha256, "evidence_sha256")
        if self.known_at < self.snapshot.observed_at:
            raise ValueError("known_at may not be before snapshot.observed_at")
        if self.valid_from_event_time > self.known_at:
            raise ValueError("valid_from_event_time may not be after known_at")
        if self.provider_id != self.snapshot.provider_id:
            raise ValueError("provider_id must match snapshot provider")
        if self.provider_fixture_id != self.snapshot.provider_fixture_id:
            raise ValueError("provider_fixture_id must match snapshot")
        if self.canonical_fixture_id != self.snapshot.fixture.canonical_fixture_id:
            raise ValueError("canonical_fixture_id must match snapshot fixture")
        if len(set(self.correction_scope)) != len(self.correction_scope):
            raise ValueError("correction_scope may not contain duplicates")
        if any(not item.strip() for item in self.correction_scope):
            raise ValueError("correction_scope items must be non-empty")
        if self.revision_kind is TruthRevisionKind.INITIAL:
            if self.supersedes_version_id is not None:
                raise ValueError("INITIAL may not supersede another version")
            if self.reason_code is not None:
                _nonempty(self.reason_code, "reason_code")
        else:
            if self.supersedes_version_id is None:
                raise ValueError("non-initial version must supersede a version")
            _nonempty(self.supersedes_version_id, "supersedes_version_id")
        if self.revision_kind in {TruthRevisionKind.CORRECTION, TruthRevisionKind.RETRACTION}:
            if self.reason_code is None:
                raise ValueError("correction/retraction requires reason_code")
            _nonempty(self.reason_code, "reason_code")
            if not self.correction_scope:
                raise ValueError("correction/retraction requires correction_scope")
        elif self.correction_scope:
            raise ValueError("correction_scope is only valid for correction/retraction")
        if self.automatic_model_promotion:
            raise ValueError("temporal truth may not promote models")
        if self.automatic_wagering:
            raise ValueError("temporal truth may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class SnapshotDelta:
    fields: tuple[str, ...]
    critical_fields: tuple[str, ...]
    identity_changed: bool

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def diff_provider_snapshots(previous: ProviderEventSnapshot, current: ProviderEventSnapshot) -> SnapshotDelta:
    fields: list[str] = []
    critical: list[str] = []
    identity_changed = False

    if previous.provider_id != current.provider_id:
        fields.append("PROVIDER_ID")
        critical.append("PROVIDER_ID")
        identity_changed = True
    if previous.provider_fixture_id != current.provider_fixture_id:
        fields.append("PROVIDER_FIXTURE_ID")
        critical.append("PROVIDER_FIXTURE_ID")
        identity_changed = True

    fixture_pairs = (
        ("SPORT", previous.fixture.sport, current.fixture.sport),
        ("CANONICAL_FIXTURE_ID", previous.fixture.canonical_fixture_id, current.fixture.canonical_fixture_id),
        ("COMPETITION", previous.fixture.competition_id, current.fixture.competition_id),
        ("HOME_ENTITY", previous.fixture.home_entity_id, current.fixture.home_entity_id),
        ("AWAY_ENTITY", previous.fixture.away_entity_id, current.fixture.away_entity_id),
        ("VENUE", previous.fixture.venue_entity_id, current.fixture.venue_entity_id),
        ("ROUND", previous.fixture.round_key, current.fixture.round_key),
    )
    for label, left, right in fixture_pairs:
        if left != right:
            fields.append(label)
            critical.append(label)
            identity_changed = True

    if previous.fixture.kickoff_utc != current.fixture.kickoff_utc:
        fields.append("KICKOFF_UTC")
        critical.append("KICKOFF_UTC")
    if previous.event_time != current.event_time:
        fields.append("EVENT_TIME")
    if previous.state != current.state:
        fields.append("EVENT_STATE")
        critical.append("EVENT_STATE")
    if previous.home_score != current.home_score:
        fields.append("HOME_SCORE")
        critical.append("HOME_SCORE")
    if previous.away_score != current.away_score:
        fields.append("AWAY_SCORE")
        critical.append("AWAY_SCORE")

    left_stats = {item.metric_id: item for item in previous.statistics}
    right_stats = {item.metric_id: item for item in current.statistics}
    for metric_id in sorted(set(left_stats) | set(right_stats)):
        if left_stats.get(metric_id) != right_stats.get(metric_id):
            fields.append(f"STAT:{metric_id}")

    left_markets = {item.key for item in previous.available_markets}
    right_markets = {item.key for item in current.available_markets}
    for key in sorted(left_markets - right_markets):
        fields.append(f"MARKET_REMOVED:{key}")
    for key in sorted(right_markets - left_markets):
        fields.append(f"MARKET_ADDED:{key}")

    return SnapshotDelta(tuple(fields), tuple(critical), identity_changed)


@dataclass(frozen=True)
class TemporalTruthPolicy:
    max_recording_delay_seconds: int
    correction_review_age_seconds: int
    require_human_review_for_critical_correction: bool = True

    def __post_init__(self) -> None:
        _nonnegative_int(self.max_recording_delay_seconds, "max_recording_delay_seconds")
        _nonnegative_int(self.correction_review_age_seconds, "correction_review_age_seconds")


@dataclass(frozen=True)
class TruthChainAssessment:
    status: TemporalTruthStatus
    reasons: tuple[str, ...]
    ordered_version_ids: tuple[str, ...]
    head_version_id: str | None
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.automatic_model_promotion:
            raise ValueError("truth-chain assessment may not promote models")
        if self.automatic_wagering:
            raise ValueError("truth-chain assessment may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def assess_truth_chain(
    versions: Iterable[ProviderTruthVersion],
    *,
    policy: TemporalTruthPolicy,
    now: datetime,
) -> TruthChainAssessment:
    _aware(now, "now")
    values = list(versions)
    if not values:
        return TruthChainAssessment(TemporalTruthStatus.BLOCK, ("NO_TRUTH_VERSIONS",), (), None)

    block: list[str] = []
    watch: list[str] = []
    if len({item.version_id for item in values}) != len(values):
        block.append("DUPLICATE_VERSION_ID")
    if len({item.fingerprint for item in values}) != len(values):
        block.append("DUPLICATE_VERSION_FINGERPRINT")

    providers = {item.provider_id for item in values}
    fixtures = {item.canonical_fixture_id for item in values}
    provider_fixtures = {item.provider_fixture_id for item in values}
    if len(providers) != 1:
        block.append("CHAIN_PROVIDER_MISMATCH")
    if len(fixtures) != 1:
        block.append("CHAIN_CANONICAL_FIXTURE_MISMATCH")
    if len(provider_fixtures) != 1:
        block.append("CHAIN_PROVIDER_FIXTURE_MISMATCH")

    ordered = sorted(values, key=lambda item: (item.known_at, item.version_id))
    if ordered[0].revision_kind is not TruthRevisionKind.INITIAL:
        block.append("CHAIN_MUST_BEGIN_WITH_INITIAL")
    if sum(item.revision_kind is TruthRevisionKind.INITIAL for item in ordered) != 1:
        block.append("CHAIN_MUST_HAVE_EXACTLY_ONE_INITIAL")

    for index, item in enumerate(ordered):
        if item.known_at > now:
            block.append(f"VERSION_FROM_FUTURE:{item.version_id}")
        if item.known_at - item.snapshot.observed_at > timedelta(seconds=policy.max_recording_delay_seconds):
            watch.append(f"RECORDING_DELAY_EXCEEDED:{item.version_id}")
        if index == 0:
            continue
        previous = ordered[index - 1]
        if item.known_at <= previous.known_at:
            block.append(f"NON_MONOTONIC_KNOWLEDGE_TIME:{item.version_id}")
        if item.supersedes_version_id != previous.version_id:
            block.append(f"NON_LINEAR_SUPERSESSION:{item.version_id}")
        delta = diff_provider_snapshots(previous.snapshot, item.snapshot)
        if delta.identity_changed:
            block.append(f"IDENTITY_REWRITE_BLOCKED:{item.version_id}")
        if item.revision_kind is TruthRevisionKind.PROGRESSION:
            if item.valid_from_event_time < previous.valid_from_event_time:
                block.append(f"PROGRESSION_RETROACTIVE_VALIDITY:{item.version_id}")
            if item.snapshot.event_time < previous.snapshot.event_time:
                block.append(f"PROGRESSION_EVENT_TIME_REGRESSION:{item.version_id}")
        if item.revision_kind in {TruthRevisionKind.CORRECTION, TruthRevisionKind.RETRACTION}:
            declared = set(item.correction_scope)
            actual = set(delta.fields)
            undeclared = sorted(actual - declared)
            if undeclared:
                block.append(f"UNDECLARED_CORRECTION_SCOPE:{item.version_id}:" + ",".join(undeclared))
            unknown = sorted(declared - actual)
            if unknown:
                watch.append(f"DECLARED_SCOPE_WITHOUT_DELTA:{item.version_id}:" + ",".join(unknown))
            age_seconds = int((item.known_at - item.valid_from_event_time).total_seconds())
            if age_seconds > policy.correction_review_age_seconds:
                watch.append(f"RETROACTIVE_CORRECTION_AGE_EXCEEDED:{item.version_id}")
            if policy.require_human_review_for_critical_correction and delta.critical_fields and not item.human_reviewed:
                block.append(f"CRITICAL_CORRECTION_NOT_HUMAN_REVIEWED:{item.version_id}")

    if block:
        status = TemporalTruthStatus.BLOCK
        reasons = tuple(dict.fromkeys(block + watch))
    elif watch:
        status = TemporalTruthStatus.WATCH
        reasons = tuple(dict.fromkeys(watch))
    else:
        status = TemporalTruthStatus.PASS
        reasons = ()
    return TruthChainAssessment(status, reasons, tuple(item.version_id for item in ordered), ordered[-1].version_id)


@dataclass(frozen=True)
class PointInTimeTruth:
    status: TemporalTruthStatus
    reasons: tuple[str, ...]
    provider_id: str
    canonical_fixture_id: str
    as_of: datetime
    event_time: datetime
    selected_version_id: str | None
    selected_version_fingerprint: str | None
    selected_snapshot_fingerprint: str | None
    retrospective_correction_applied: bool
    future_knowledge_used: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        _aware(self.as_of, "as_of")
        _aware(self.event_time, "event_time")
        if self.future_knowledge_used:
            raise ValueError("point-in-time truth may not use future knowledge")
        if self.automatic_model_promotion:
            raise ValueError("point-in-time truth may not promote models")
        if self.automatic_wagering:
            raise ValueError("point-in-time truth may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def resolve_point_in_time_truth(
    versions: Iterable[ProviderTruthVersion],
    *,
    provider_id: str,
    canonical_fixture_id: str,
    as_of: datetime,
    event_time: datetime,
    now: datetime,
    policy: TemporalTruthPolicy,
) -> PointInTimeTruth:
    provider_id = _nonempty(provider_id, "provider_id")
    canonical_fixture_id = _nonempty(canonical_fixture_id, "canonical_fixture_id")
    _aware(as_of, "as_of")
    _aware(event_time, "event_time")
    _aware(now, "now")
    if as_of > now:
        return PointInTimeTruth(
            TemporalTruthStatus.BLOCK,
            ("AS_OF_FROM_FUTURE",),
            provider_id,
            canonical_fixture_id,
            as_of,
            event_time,
            None,
            None,
            None,
            False,
        )

    scoped = tuple(
        item for item in versions
        if item.provider_id == provider_id and item.canonical_fixture_id == canonical_fixture_id
    )
    chain = assess_truth_chain(scoped, policy=policy, now=now)
    if chain.status is TemporalTruthStatus.BLOCK:
        return PointInTimeTruth(
            TemporalTruthStatus.BLOCK,
            tuple(dict.fromkeys(("TRUTH_CHAIN_INVALID",) + chain.reasons)),
            provider_id,
            canonical_fixture_id,
            as_of,
            event_time,
            None,
            None,
            None,
            False,
        )

    eligible = [
        item for item in scoped
        if item.known_at <= as_of and item.valid_from_event_time <= event_time
    ]
    if not eligible:
        return PointInTimeTruth(
            TemporalTruthStatus.BLOCK,
            ("NO_TRUTH_KNOWN_AS_OF_QUERY",),
            provider_id,
            canonical_fixture_id,
            as_of,
            event_time,
            None,
            None,
            None,
            False,
        )

    selected = max(eligible, key=lambda item: (item.known_at, item.version_id))
    retrospective = (
        selected.revision_kind in {TruthRevisionKind.CORRECTION, TruthRevisionKind.RETRACTION}
        and selected.known_at > event_time
    )
    reasons = list(chain.reasons if chain.status is TemporalTruthStatus.WATCH else ())
    if retrospective:
        reasons.append("RETROSPECTIVE_CORRECTION_APPLIED")
    status = TemporalTruthStatus.WATCH if reasons else TemporalTruthStatus.PASS
    return PointInTimeTruth(
        status,
        tuple(dict.fromkeys(reasons)),
        provider_id,
        canonical_fixture_id,
        as_of,
        event_time,
        selected.version_id,
        selected.fingerprint,
        selected.snapshot.fingerprint,
        retrospective,
    )


@dataclass(frozen=True)
class DecisionEvidenceFreeze:
    decision_id: str
    provider_id: str
    canonical_fixture_id: str
    decision_at: datetime
    truth_version_id: str
    truth_version_fingerprint: str
    snapshot_fingerprint: str
    model_version: str
    market_key: str | None
    evidence_sha256: str
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.decision_id, "decision_id"),
            (self.provider_id, "provider_id"),
            (self.canonical_fixture_id, "canonical_fixture_id"),
            (self.truth_version_id, "truth_version_id"),
            (self.truth_version_fingerprint, "truth_version_fingerprint"),
            (self.snapshot_fingerprint, "snapshot_fingerprint"),
            (self.model_version, "model_version"),
        ):
            _nonempty(value, name)
        _aware(self.decision_at, "decision_at")
        _sha256(self.truth_version_fingerprint, "truth_version_fingerprint")
        _sha256(self.snapshot_fingerprint, "snapshot_fingerprint")
        _sha256(self.evidence_sha256, "evidence_sha256")
        if self.market_key is not None:
            _nonempty(self.market_key, "market_key")
        if self.automatic_wagering:
            raise ValueError("decision evidence freeze may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class DecisionEvidenceAssessment:
    status: TemporalTruthStatus
    reasons: tuple[str, ...]
    freeze_fingerprint: str
    historical_truth_fingerprint: str | None
    temporal_leakage_detected: bool
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.automatic_model_promotion:
            raise ValueError("decision assessment may not promote models")
        if self.automatic_wagering:
            raise ValueError("decision assessment may not enable wagering")


def validate_decision_evidence_freeze(
    freeze: DecisionEvidenceFreeze,
    versions: Iterable[ProviderTruthVersion],
    *,
    now: datetime,
    policy: TemporalTruthPolicy,
) -> DecisionEvidenceAssessment:
    _aware(now, "now")
    if freeze.decision_at > now:
        return DecisionEvidenceAssessment(
            TemporalTruthStatus.BLOCK,
            ("DECISION_FROM_FUTURE",),
            freeze.fingerprint,
            None,
            True,
        )
    values = tuple(versions)
    candidates = [item for item in values if item.version_id == freeze.truth_version_id]
    if len(candidates) != 1:
        return DecisionEvidenceAssessment(
            TemporalTruthStatus.BLOCK,
            ("FROZEN_TRUTH_VERSION_NOT_UNIQUE",),
            freeze.fingerprint,
            None,
            True,
        )
    frozen = candidates[0]
    reasons: list[str] = []
    leakage = False
    if frozen.provider_id != freeze.provider_id or frozen.canonical_fixture_id != freeze.canonical_fixture_id:
        reasons.append("FROZEN_TRUTH_SCOPE_MISMATCH")
        leakage = True
    if frozen.fingerprint != freeze.truth_version_fingerprint:
        reasons.append("FROZEN_TRUTH_FINGERPRINT_MISMATCH")
        leakage = True
    if frozen.snapshot.fingerprint != freeze.snapshot_fingerprint:
        reasons.append("FROZEN_SNAPSHOT_FINGERPRINT_MISMATCH")
        leakage = True
    if frozen.known_at > freeze.decision_at or frozen.snapshot.observed_at > freeze.decision_at:
        reasons.append("FUTURE_KNOWLEDGE_IN_DECISION_EVIDENCE")
        leakage = True

    historical = resolve_point_in_time_truth(
        values,
        provider_id=freeze.provider_id,
        canonical_fixture_id=freeze.canonical_fixture_id,
        as_of=freeze.decision_at,
        event_time=freeze.decision_at,
        now=now,
        policy=policy,
    )
    if historical.status is TemporalTruthStatus.BLOCK:
        reasons.append("HISTORICAL_TRUTH_NOT_RECONSTRUCTABLE")
        leakage = True
    elif historical.selected_version_id != freeze.truth_version_id:
        reasons.append("DECISION_DID_NOT_USE_LATEST_KNOWN_TRUTH")
        leakage = True

    status = TemporalTruthStatus.BLOCK if leakage else TemporalTruthStatus.PASS
    return DecisionEvidenceAssessment(
        status,
        tuple(dict.fromkeys(reasons)),
        freeze.fingerprint,
        historical.fingerprint if historical.selected_version_id is not None else None,
        leakage,
    )


class RevisionImpactLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class PostDecisionRevisionImpact:
    status: TemporalTruthStatus
    impact_level: RevisionImpactLevel
    reasons: tuple[str, ...]
    affected_fields: tuple[str, ...]
    correction_version_ids: tuple[str, ...]
    reanalysis_required: bool
    original_analysis_quality_determined: bool = False
    automatic_model_promotion: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.original_analysis_quality_determined:
            raise ValueError("revision impact may not determine original analysis quality")
        if self.automatic_model_promotion:
            raise ValueError("revision impact may not promote models")
        if self.automatic_wagering:
            raise ValueError("revision impact may not enable wagering")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def assess_post_decision_revision_impact(
    freeze: DecisionEvidenceFreeze,
    versions: Iterable[ProviderTruthVersion],
    *,
    now: datetime,
    policy: TemporalTruthPolicy,
) -> PostDecisionRevisionImpact:
    values = tuple(versions)
    decision_assessment = validate_decision_evidence_freeze(freeze, values, now=now, policy=policy)
    if decision_assessment.status is TemporalTruthStatus.BLOCK:
        return PostDecisionRevisionImpact(
            TemporalTruthStatus.BLOCK,
            RevisionImpactLevel.CRITICAL,
            tuple(dict.fromkeys(("DECISION_EVIDENCE_INVALID",) + decision_assessment.reasons)),
            (),
            (),
            True,
        )
    frozen = next(item for item in values if item.version_id == freeze.truth_version_id)
    corrections = sorted(
        (
            item for item in values
            if item.provider_id == freeze.provider_id
            and item.canonical_fixture_id == freeze.canonical_fixture_id
            and item.known_at > freeze.decision_at
            and item.revision_kind in {TruthRevisionKind.CORRECTION, TruthRevisionKind.RETRACTION}
        ),
        key=lambda item: (item.known_at, item.version_id),
    )
    if not corrections:
        return PostDecisionRevisionImpact(
            TemporalTruthStatus.PASS,
            RevisionImpactLevel.NONE,
            (),
            (),
            (),
            False,
        )

    affected: set[str] = set()
    for item in corrections:
        affected.update(item.correction_scope)
    critical_identity = any(field in affected for field in {
        "SPORT", "CANONICAL_FIXTURE_ID", "COMPETITION", "HOME_ENTITY", "AWAY_ENTITY",
        "PROVIDER_ID", "PROVIDER_FIXTURE_ID",
    })
    score_or_state = any(field in affected for field in {"HOME_SCORE", "AWAY_SCORE", "EVENT_STATE"})
    kickoff = "KICKOFF_UTC" in affected
    market = any(field.startswith("MARKET_") for field in affected)
    stat = any(field.startswith("STAT:") for field in affected)

    if critical_identity:
        level = RevisionImpactLevel.CRITICAL
    elif score_or_state or kickoff:
        level = RevisionImpactLevel.HIGH
    elif market or stat:
        level = RevisionImpactLevel.MEDIUM
    else:
        level = RevisionImpactLevel.LOW
    reanalysis = level in {RevisionImpactLevel.MEDIUM, RevisionImpactLevel.HIGH, RevisionImpactLevel.CRITICAL}
    reasons = ["POST_DECISION_PROVIDER_CORRECTION"]
    if reanalysis:
        reasons.append("REANALYSIS_REQUIRED")
    reasons.append("ORIGINAL_ANALYSIS_QUALITY_NOT_DETERMINED_BY_CORRECTION")
    return PostDecisionRevisionImpact(
        TemporalTruthStatus.WATCH,
        level,
        tuple(reasons),
        tuple(sorted(affected)),
        tuple(item.version_id for item in corrections),
        reanalysis,
    )
