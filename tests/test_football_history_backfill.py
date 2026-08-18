from pathlib import Path

from app.application.football.history_backfill import (
    HistoricalBackfillCheckpoint,
    HistoricalBackfillPolicy,
    HistoricalFixtureBackfillService,
)


class FakeClient:
    def __init__(self, payload_by_date, *, daily_remaining=100):
        self.payload_by_date = payload_by_date
        self.daily_remaining = daily_remaining
        self.calls = []

    def get(self, endpoint, params=None):
        assert endpoint == "/fixtures"
        day = params["date"]
        self.calls.append(day)
        self.daily_remaining -= 1
        value = self.payload_by_date.get(day, [])
        if isinstance(value, Exception):
            raise value
        return {"response": value}


class FakeRepository:
    def __init__(self):
        self.reconciled = []
        self.upserted = []

    def reconcile_records_for_date(self, day, records):
        self.reconciled.append((day, list(records)))

    def upsert_records(self, records):
        self.upserted.append(list(records))


def fixture(fid, day="2026-08-01"):
    return {
        "fixture": {"id": fid, "date": f"{day}T12:00:00+00:00", "status": {"short": "FT"}},
        "league": {"id": 50, "name": "Liga", "country": "Colombia", "season": 2026, "round": "1"},
        "teams": {"home": {"id": 1000 + fid * 2, "name": f"H{fid}"}, "away": {"id": 1001 + fid * 2, "name": f"A{fid}"}},
        "goals": {"home": 1, "away": 0},
    }


def test_policy_dates_are_inclusive_and_validated():
    policy = HistoricalBackfillPolicy("2026-08-01", "2026-08-03", max_calls=2, quota_reserve=10)
    assert policy.dates() == ("2026-08-01", "2026-08-02", "2026-08-03")


def test_checkpoint_round_trip_is_atomic_and_deduplicated(tmp_path):
    path = tmp_path / "state.json"
    checkpoint = HistoricalBackfillCheckpoint(completed_dates=["2026-08-02", "2026-08-01", "2026-08-01"])
    checkpoint.save(path)
    loaded = HistoricalBackfillCheckpoint.load(path)
    assert loaded.completed_dates == ["2026-08-01", "2026-08-02"]
    assert loaded.updated_at_utc is not None
    assert not (tmp_path / "state.json.tmp").exists()


def test_backfill_is_resumable_and_reconciles_complete_dates(tmp_path):
    client = FakeClient({
        "2026-08-01": [fixture(1, "2026-08-01")],
        "2026-08-02": [fixture(2, "2026-08-02")],
    })
    repo = FakeRepository()
    checkpoint = tmp_path / "checkpoint.json"
    service = HistoricalFixtureBackfillService(client, repo)
    result = service.run(
        HistoricalBackfillPolicy("2026-08-01", "2026-08-02", max_calls=1, quota_reserve=0),
        checkpoint_path=checkpoint,
    )
    assert result.attempted_dates == 1
    assert result.stopped_reason == "max_calls_reached"
    assert [day for day, _ in repo.reconciled] == ["2026-08-01"]

    result2 = service.run(
        HistoricalBackfillPolicy("2026-08-01", "2026-08-02", max_calls=2, quota_reserve=0),
        checkpoint_path=checkpoint,
    )
    assert result2.skipped_dates == 1
    assert result2.completed_dates == 2
    assert client.calls == ["2026-08-01", "2026-08-02"]


def test_backfill_stops_before_burning_quota_reserve(tmp_path):
    client = FakeClient({"2026-08-01": [fixture(1)]}, daily_remaining=20)
    repo = FakeRepository()
    result = HistoricalFixtureBackfillService(client, repo).run(
        HistoricalBackfillPolicy("2026-08-01", "2026-08-01", max_calls=5, quota_reserve=20),
        checkpoint_path=tmp_path / "checkpoint.json",
    )
    assert result.attempted_dates == 0
    assert result.stopped_reason == "quota_reserve_reached"
    assert client.calls == []


def test_backfill_partial_ingestion_uses_non_destructive_upsert(tmp_path):
    malformed = {"fixture": {"id": 9}}
    client = FakeClient({"2026-08-01": [fixture(1), malformed]})
    repo = FakeRepository()
    result = HistoricalFixtureBackfillService(client, repo).run(
        HistoricalBackfillPolicy("2026-08-01", "2026-08-01", quota_reserve=0),
        checkpoint_path=tmp_path / "checkpoint.json",
    )
    assert result.accepted_records == 1
    assert result.rejected_records == 1
    assert result.partial_dates == 1
    assert result.completed_dates == 0
    assert result.stopped_reason == "date_range_processed_with_partials"
    assert len(repo.upserted) == 1
    assert repo.reconciled == []
    checkpoint = HistoricalBackfillCheckpoint.load(tmp_path / "checkpoint.json")
    assert checkpoint.completed_dates == []
    assert checkpoint.failed_dates["2026-08-01"] == "partial_ingestion"


def test_backfill_records_sanitized_error_type_and_can_resume(tmp_path):
    client = FakeClient({"2026-08-01": RuntimeError("secret should not persist")})
    repo = FakeRepository()
    state = tmp_path / "checkpoint.json"
    result = HistoricalFixtureBackfillService(client, repo).run(
        HistoricalBackfillPolicy("2026-08-01", "2026-08-01", quota_reserve=0),
        checkpoint_path=state,
    )
    assert result.stopped_reason == "provider_or_persistence_error"
    raw = state.read_text(encoding="utf-8")
    assert "RuntimeError" in raw
    assert "secret should not persist" not in raw


def test_partial_backfill_date_is_retried_and_only_then_completed(tmp_path):
    state = tmp_path / "checkpoint.json"
    malformed = {"fixture": {"id": 9}}
    client = FakeClient({"2026-08-01": [fixture(1), malformed]})
    repo = FakeRepository()
    service = HistoricalFixtureBackfillService(client, repo)

    first = service.run(
        HistoricalBackfillPolicy("2026-08-01", "2026-08-01", quota_reserve=0),
        checkpoint_path=state,
    )
    assert first.completed_dates == 0

    client.payload_by_date["2026-08-01"] = [fixture(1)]
    second = service.run(
        HistoricalBackfillPolicy("2026-08-01", "2026-08-01", quota_reserve=0),
        checkpoint_path=state,
    )
    assert second.completed_dates == 1
    assert second.partial_dates == 0
    checkpoint = HistoricalBackfillCheckpoint.load(state)
    assert checkpoint.completed_dates == ["2026-08-01"]
    assert "2026-08-01" not in checkpoint.failed_dates
    assert client.calls == ["2026-08-01", "2026-08-01"]


def test_backfill_uses_one_mutual_exclusion_lock_per_attempted_date(tmp_path):
    entered = []
    exited = []

    class Lock:
        def __init__(self, day): self.day = day
        def __enter__(self): entered.append(self.day); return self
        def __exit__(self, *args): exited.append(self.day); return False

    client = FakeClient({"2026-08-01": [fixture(1)]})
    repo = FakeRepository()
    result = HistoricalFixtureBackfillService(
        client, repo, date_lock_factory=lambda day: Lock(day)
    ).run(
        HistoricalBackfillPolicy("2026-08-01", "2026-08-01", quota_reserve=0),
        checkpoint_path=tmp_path / "checkpoint.json",
    )
    assert result.completed_dates == 1
    assert entered == ["2026-08-01"]
    assert exited == ["2026-08-01"]
