from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from datetime import date as date_type, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Iterable

from app.providers.api_football.fixture_service import get_fixture_ingestion_by_date


def _parse_date(value: str) -> date_type:
    try:
        return date_type.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("date must use YYYY-MM-DD") from error


@dataclass(frozen=True)
class HistoricalBackfillPolicy:
    start_date: str
    end_date: str
    max_calls: int = 70
    quota_reserve: int = 20

    def __post_init__(self) -> None:
        start = _parse_date(self.start_date)
        end = _parse_date(self.end_date)
        if end < start:
            raise ValueError("end_date must be on or after start_date")
        if isinstance(self.max_calls, bool) or not isinstance(self.max_calls, int) or self.max_calls <= 0:
            raise ValueError("max_calls must be a positive integer")
        if isinstance(self.quota_reserve, bool) or not isinstance(self.quota_reserve, int) or self.quota_reserve < 0:
            raise ValueError("quota_reserve must be a non-negative integer")

    def dates(self) -> tuple[str, ...]:
        start = _parse_date(self.start_date)
        end = _parse_date(self.end_date)
        count = (end - start).days + 1
        return tuple((start + timedelta(days=offset)).isoformat() for offset in range(count))


@dataclass
class HistoricalBackfillCheckpoint:
    completed_dates: list[str] = field(default_factory=list)
    failed_dates: dict[str, str] = field(default_factory=dict)
    updated_at_utc: str | None = None

    @classmethod
    def load(cls, path: str | Path) -> "HistoricalBackfillCheckpoint":
        target = Path(path)
        if not target.exists():
            return cls()
        raw = json.loads(target.read_text(encoding="utf-8"))
        return cls(
            completed_dates=list(raw.get("completed_dates", [])),
            failed_dates=dict(raw.get("failed_dates", {})),
            updated_at_utc=raw.get("updated_at_utc"),
        )

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.completed_dates = sorted(set(self.completed_dates))
        self.updated_at_utc = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(target)


@dataclass(frozen=True)
class HistoricalBackfillRunResult:
    requested_dates: int
    attempted_dates: int
    completed_dates: int
    partial_dates: int
    skipped_dates: int
    accepted_records: int
    rejected_records: int
    stopped_reason: str
    daily_remaining: int | None


class HistoricalFixtureBackfillService:
    """Quota-conscious, resumable historical fixture acquisition.

    One date consumes one `/fixtures?date=...` API call. The service intentionally
    persists fixture/result history only; detailed live snapshots are *not* fabricated
    from final statistics. Partial provider responses are upserted but never reconciled
    destructively.
    """

    def __init__(self, client, repository, *, date_lock_factory=None) -> None:
        self.client = client
        self.repository = repository
        self.date_lock_factory = date_lock_factory

    def run(
        self,
        policy: HistoricalBackfillPolicy,
        *,
        checkpoint_path: str | Path,
    ) -> HistoricalBackfillRunResult:
        checkpoint = HistoricalBackfillCheckpoint.load(checkpoint_path)
        completed = set(checkpoint.completed_dates)
        attempted = 0
        accepted = 0
        rejected = 0
        skipped = 0
        partial_dates = 0
        stopped_reason = "date_range_complete"

        for day in policy.dates():
            if day in completed:
                skipped += 1
                continue
            if attempted >= policy.max_calls:
                stopped_reason = "max_calls_reached"
                break
            remaining = getattr(self.client, "daily_remaining", None)
            if remaining is not None and remaining <= policy.quota_reserve:
                stopped_reason = "quota_reserve_reached"
                break

            try:
                lock = self.date_lock_factory(day) if self.date_lock_factory is not None else nullcontext()
                with lock:
                    ingestion = get_fixture_ingestion_by_date(self.client, day)
                    if ingestion.rejected_count == 0:
                        self.repository.reconcile_records_for_date(day, ingestion.records)
                    else:
                        # Partial provider payloads are persisted non-destructively but are
                        # deliberately NOT checkpointed as complete. The date must be retried
                        # on a later run so malformed/missing provider rows cannot silently
                        # create a permanent historical hole.
                        self.repository.upsert_records(ingestion.records)
            except Exception as error:
                checkpoint.failed_dates[day] = type(error).__name__
                checkpoint.save(checkpoint_path)
                stopped_reason = "provider_or_persistence_error"
                break

            attempted += 1
            accepted += ingestion.accepted_count
            rejected += ingestion.rejected_count
            if ingestion.rejected_count == 0:
                completed.add(day)
                checkpoint.completed_dates = sorted(completed)
                checkpoint.failed_dates.pop(day, None)
            else:
                partial_dates += 1
                checkpoint.failed_dates[day] = "partial_ingestion"
            checkpoint.save(checkpoint_path)

        if stopped_reason == "date_range_complete" and partial_dates:
            stopped_reason = "date_range_processed_with_partials"

        return HistoricalBackfillRunResult(
            requested_dates=len(policy.dates()),
            attempted_dates=attempted,
            completed_dates=len(completed.intersection(policy.dates())),
            partial_dates=partial_dates,
            skipped_dates=skipped,
            accepted_records=accepted,
            rejected_records=rejected,
            stopped_reason=stopped_reason,
            daily_remaining=getattr(self.client, "daily_remaining", None),
        )
