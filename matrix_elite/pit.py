from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class PITViolation:
    index: int
    code: str
    detail: str = ""


@dataclass(frozen=True)
class PITRecord:
    record_key: str
    provider: str
    sport: str
    competition: str
    market: str
    observed_at: datetime
    available_at: datetime
    event_start_at: datetime
    revision_id: str
    revision_number: int
    payload_sha256: str
    supersedes_revision_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("record_key", "provider", "sport", "competition", "market", "revision_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name.upper()}_REQUIRED")
        _aware(self.observed_at, "OBSERVED_AT")
        _aware(self.available_at, "AVAILABLE_AT")
        _aware(self.event_start_at, "EVENT_START_AT")
        if self.available_at < self.observed_at:
            raise ValueError("AVAILABLE_BEFORE_OBSERVED")
        if type(self.revision_number) is not int or self.revision_number < 1:
            raise ValueError("REVISION_NUMBER_INVALID")
        _sha(self.payload_sha256, "PAYLOAD_SHA256")
        if self.supersedes_revision_id == self.revision_id:
            raise ValueError("REVISION_SELF_SUPERSESSION")

    @property
    def natural_key(self) -> tuple[str, str]:
        return (self.provider, self.record_key)


@dataclass(frozen=True)
class PITManifest:
    schema: str
    as_of_utc: str
    record_count: int
    provider_count: int
    sports: tuple[str, ...]
    min_available_at_utc: str | None
    max_available_at_utc: str | None
    snapshot_sha256: str


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")
    return value


def _sha(value: str, name: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{name}_REQUIRED")
    int(value, 16)
    return value.lower()


def audit_point_in_time(records: Iterable[Mapping[str, Any]], *, as_of: datetime) -> tuple[PITViolation, ...]:
    """Reject rows that were not actually available at a prediction cutoff."""
    cutoff = _aware(as_of, "AS_OF")
    out: list[PITViolation] = []
    for i, row in enumerate(records):
        observed = row.get("observed_at")
        available = row.get("available_at")
        if not isinstance(observed, datetime) or not isinstance(available, datetime):
            out.append(PITViolation(i, "MISSING_OR_INVALID_TIME"))
            continue
        _aware(observed, "OBSERVED_AT")
        _aware(available, "AVAILABLE_AT")
        if available > cutoff:
            out.append(PITViolation(i, "NOT_AVAILABLE_AS_OF"))
        if available < observed:
            out.append(PITViolation(i, "AVAILABLE_BEFORE_OBSERVED"))
    return tuple(out)


def valid_history_windows(prior_event_count: int, windows=(5, 10, 20, 30, 50)) -> dict[int, bool]:
    if type(prior_event_count) is not int or prior_event_count < 0:
        raise ValueError("PRIOR_EVENT_COUNT_INVALID")
    return {w: prior_event_count >= w for w in windows}


def audit_revision_graph(records: Sequence[PITRecord]) -> tuple[PITViolation, ...]:
    """Validate revision lineage without assuming later revisions existed earlier."""
    violations: list[PITViolation] = []
    by_revision: dict[str, tuple[int, PITRecord]] = {}
    seen_numbers: set[tuple[str, str, int]] = set()

    for i, rec in enumerate(records):
        if rec.revision_id in by_revision:
            violations.append(PITViolation(i, "DUPLICATE_REVISION_ID", rec.revision_id))
        else:
            by_revision[rec.revision_id] = (i, rec)
        num_key = (rec.provider, rec.record_key, rec.revision_number)
        if num_key in seen_numbers:
            violations.append(PITViolation(i, "DUPLICATE_REVISION_NUMBER", str(num_key)))
        seen_numbers.add(num_key)

    child_counts: dict[str, int] = {}
    for rec in records:
        if rec.supersedes_revision_id is not None:
            child_counts[rec.supersedes_revision_id] = child_counts.get(rec.supersedes_revision_id, 0) + 1
    for parent_id, count in child_counts.items():
        if count > 1:
            parent_entry = by_revision.get(parent_id)
            idx = parent_entry[0] if parent_entry else -1
            violations.append(PITViolation(idx, "REVISION_FORK", parent_id))

    for i, rec in enumerate(records):
        parent_id = rec.supersedes_revision_id
        if parent_id is None:
            if rec.revision_number != 1:
                violations.append(PITViolation(i, "REVISION_ROOT_NUMBER_NOT_ONE", rec.revision_id))
            continue
        parent_entry = by_revision.get(parent_id)
        if parent_entry is None:
            violations.append(PITViolation(i, "SUPERSEDED_REVISION_NOT_FOUND", parent_id))
            continue
        _, parent = parent_entry
        if parent.natural_key != rec.natural_key:
            violations.append(PITViolation(i, "CROSS_KEY_SUPERSESSION", parent_id))
        if parent.revision_number >= rec.revision_number:
            violations.append(PITViolation(i, "NON_MONOTONIC_REVISION_NUMBER", parent_id))
        elif rec.revision_number != parent.revision_number + 1:
            violations.append(PITViolation(i, "REVISION_NUMBER_GAP", parent_id))
        if parent.available_at > rec.available_at:
            violations.append(PITViolation(i, "SUPERSESSION_TIME_TRAVEL", parent_id))

    # Cycle detection independent of revision numbers.
    for i, rec in enumerate(records):
        seen: set[str] = set()
        current = rec
        while current.supersedes_revision_id is not None:
            parent_id = current.supersedes_revision_id
            if parent_id in seen or parent_id == rec.revision_id:
                violations.append(PITViolation(i, "REVISION_CYCLE", rec.revision_id))
                break
            seen.add(parent_id)
            parent_entry = by_revision.get(parent_id)
            if parent_entry is None:
                break
            current = parent_entry[1]
    return tuple(violations)


def snapshot_as_of(records: Sequence[PITRecord], *, as_of: datetime) -> tuple[PITRecord, ...]:
    """Return the latest *available* revision for each provider/record key at cutoff.

    A revision created after `as_of` can never replace the earlier revision in a
    historical snapshot, even when it carries a higher revision number.
    """
    cutoff = _aware(as_of, "AS_OF")
    graph_errors = audit_revision_graph(records)
    if graph_errors:
        raise ValueError("REVISION_GRAPH_INVALID:" + ",".join(sorted({v.code for v in graph_errors})))

    admissible = [r for r in records if r.available_at <= cutoff]
    latest: dict[tuple[str, str], PITRecord] = {}
    for rec in admissible:
        key = rec.natural_key
        prior = latest.get(key)
        if prior is None or (rec.revision_number, rec.available_at, rec.revision_id) > (
            prior.revision_number,
            prior.available_at,
            prior.revision_id,
        ):
            latest[key] = rec
    return tuple(sorted(latest.values(), key=lambda r: (r.provider, r.record_key)))


def audit_prediction_cutoff(records: Sequence[PITRecord], *, prediction_at: datetime) -> tuple[PITViolation, ...]:
    """Audit leakage relative to the prediction decision timestamp."""
    cutoff = _aware(prediction_at, "PREDICTION_AT")
    out: list[PITViolation] = list(audit_revision_graph(records))
    for i, rec in enumerate(records):
        if rec.available_at > cutoff:
            out.append(PITViolation(i, "LEAKAGE_AVAILABLE_AFTER_PREDICTION", rec.revision_id))
        if rec.event_start_at <= cutoff and rec.market != "POST_EVENT":
            # Historical rows are allowed; only flag rows whose key explicitly
            # describes the same event if the caller marks it as CURRENT_EVENT.
            if rec.record_key.startswith("CURRENT_EVENT:"):
                out.append(PITViolation(i, "CURRENT_EVENT_ALREADY_STARTED", rec.record_key))
    return tuple(out)


def coverage_cube(records: Sequence[PITRecord]) -> dict[tuple[str, str, str, int], int]:
    """Counts latest record revisions by sport/competition/market/calendar year."""
    latest: dict[tuple[str, str], PITRecord] = {}
    for rec in records:
        prior = latest.get(rec.natural_key)
        if prior is None or (rec.revision_number, rec.available_at) > (prior.revision_number, prior.available_at):
            latest[rec.natural_key] = rec
    cube: dict[tuple[str, str, str, int], int] = {}
    for rec in latest.values():
        key = (rec.sport, rec.competition, rec.market, rec.event_start_at.year)
        cube[key] = cube.get(key, 0) + 1
    return dict(sorted(cube.items()))


def audit_minimum_coverage(
    records: Sequence[PITRecord],
    *,
    requirements: Mapping[tuple[str, str, str, int], int],
) -> dict[tuple[str, str, str, int], dict[str, int | bool]]:
    cube = coverage_cube(records)
    result: dict[tuple[str, str, str, int], dict[str, int | bool]] = {}
    for key, minimum in requirements.items():
        if type(minimum) is not int or minimum < 1:
            raise ValueError("COVERAGE_MINIMUM_INVALID")
        actual = cube.get(key, 0)
        result[key] = {"actual": actual, "minimum": minimum, "pass": actual >= minimum}
    return result


def _record_for_hash(rec: PITRecord) -> dict[str, Any]:
    data = asdict(rec)
    for k in ("observed_at", "available_at", "event_start_at"):
        data[k] = data[k].isoformat()
    return data


def snapshot_manifest(records: Sequence[PITRecord], *, as_of: datetime) -> PITManifest:
    snap = snapshot_as_of(records, as_of=as_of)
    canonical = [_record_for_hash(r) for r in snap]
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    available = [r.available_at for r in snap]
    return PITManifest(
        schema="MATRIX_PIT_SNAPSHOT_MANIFEST_R2",
        as_of_utc=_aware(as_of, "AS_OF").isoformat(),
        record_count=len(snap),
        provider_count=len({r.provider for r in snap}),
        sports=tuple(sorted({r.sport for r in snap})),
        min_available_at_utc=min(available).isoformat() if available else None,
        max_available_at_utc=max(available).isoformat() if available else None,
        snapshot_sha256=sha256(encoded).hexdigest(),
    )
