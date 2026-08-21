from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
import pytest

from app.application.football.identity_lifecycle import (
    append_football_identity_alias,
    append_football_identity_rename,
    append_football_temporal_provider_binding,
)
from app.core.append_only_tail_guard import (
    APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN,
    SQLiteAppendOnlyTailGuard,
)
from app.core.canonical_identity import SQLiteCanonicalIdentityRegistry
from app.core.canonical_identity_lifecycle import SQLiteCanonicalIdentityLifecycleLedger
from app.core.provider_identity_lifecycle import SQLiteTemporalProviderIdentityLedger

UTC = timezone.utc

def at(day: int) -> datetime:
    return datetime(2026, 8, day, 12, tzinfo=UTC)

def registry(tmp_path: Path, stem: str):
    store = SQLiteCanonicalIdentityRegistry(tmp_path / f'{stem}-registry.db')
    first = store.build_entity(sport='football', entity_type='team', canonical_key=f'TEAM:F:{stem}:A', display_name=f'{stem} A')
    second = store.build_entity(sport='football', entity_type='team', canonical_key=f'TEAM:F:{stem}:B', display_name=f'{stem} B')
    store.register(first)
    store.register(second)
    return store, first, second

def test_file_backed_tail_guard_creates_external_anchor(tmp_path):
    database = tmp_path / 'guard.db'
    connection = sqlite3.connect(database, isolation_level=None)
    guard = SQLiteAppendOnlyTailGuard(table_name='test_tail_guard', ledger_name='test-ledger')
    guard.ensure_schema(connection)
    guard.bootstrap_if_pristine(connection, records=())
    guard.append(connection, record_id='a', record_payload_sha256='a' * 64)
    connection.close()
    anchor = Path(str(database.resolve()) + '.test_tail_guard.init-anchor')
    assert anchor.exists()

def test_canonical_guard_and_state_loss_cannot_rebaseline(tmp_path):
    store, first, _ = registry(tmp_path, 'CANONDOUBLE')
    path = tmp_path / 'canonical.db'
    ledger = SQLiteCanonicalIdentityLifecycleLedger(path, identity_registry=store)
    alias = append_football_identity_alias(ledger=ledger, canonical_id=first.canonical_id, entity_type='team', alias='Alias', effective_at=at(1), known_at=at(1), reason_code='ALIAS')
    rename = append_football_identity_rename(ledger=ledger, canonical_id=first.canonical_id, entity_type='team', display_name='Renamed', effective_at=at(2), known_at=at(2), reason_code='RENAME', previous_event_id=alias.event_id, human_reviewed=True)
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM canonical_identity_lifecycle WHERE event_id = ?', (rename.event_id,))
        connection.execute('DROP TABLE canonical_identity_lifecycle_tail_guard')
        connection.execute('DROP TABLE canonical_identity_lifecycle_tail_guard_state')
        connection.commit()
    with pytest.raises(ValueError, match=APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN):
        SQLiteCanonicalIdentityLifecycleLedger(path, identity_registry=store)

def test_provider_guard_and_state_loss_cannot_rebaseline(tmp_path):
    store, first, second = registry(tmp_path, 'PROVIDERDOUBLE')
    path = tmp_path / 'provider.db'
    ledger = SQLiteTemporalProviderIdentityLedger(path, identity_registry=store)
    append_football_temporal_provider_binding(ledger=ledger, entity_type='team', provider_key='provider-a', provider_entity_id='team-1', canonical_id=first.canonical_id, valid_from=at(1), valid_to=None, known_at=at(1), resolution_method='provider_stable_id', reason_code='INITIAL', human_reviewed=False)
    _, successor = ledger.remap(sport='football', entity_type='team', provider_key='provider-a', provider_entity_id='team-1', new_canonical_id=second.canonical_id, remap_at=at(10), known_at=at(12), resolution_method='manual_verified', reason_code='REMAP', human_reviewed=True)
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM temporal_provider_identity_binding WHERE binding_id = ?', (successor.binding_id,))
        connection.execute('DROP TABLE temporal_provider_identity_tail_guard')
        connection.execute('DROP TABLE temporal_provider_identity_tail_guard_state')
        connection.commit()
    with pytest.raises(ValueError, match=APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN):
        SQLiteTemporalProviderIdentityLedger(path, identity_registry=store)

def test_external_anchor_detects_complete_local_ledger_wipe(tmp_path):
    store, first, _ = registry(tmp_path, 'FULLWIPE')
    path = tmp_path / 'full-wipe.db'
    ledger = SQLiteCanonicalIdentityLifecycleLedger(path, identity_registry=store)
    append_football_identity_alias(ledger=ledger, canonical_id=first.canonical_id, entity_type='team', alias='Alias', effective_at=at(1), known_at=at(1), reason_code='ALIAS')
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM canonical_identity_lifecycle')
        connection.execute('DROP TABLE canonical_identity_lifecycle_tail_guard')
        connection.execute('DROP TABLE canonical_identity_lifecycle_tail_guard_state')
        connection.commit()
    with pytest.raises(ValueError, match=APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN):
        SQLiteCanonicalIdentityLifecycleLedger(path, identity_registry=store)

def test_concurrent_canonical_append_cannot_create_fork(tmp_path):
    store, first, _ = registry(tmp_path, 'CONCURRENT')
    class BarrierLedger(SQLiteCanonicalIdentityLifecycleLedger):
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        waiters = 0
        def _events_for(self, canonical_id):
            events = super()._events_for(canonical_id)
            if threading.current_thread().name.startswith('matrix-v7r-chain-'):
                wait = False
                with self.lock:
                    if self.waiters < 2:
                        self.waiters += 1
                        wait = True
                if wait:
                    self.barrier.wait(timeout=15)
            return events
    path = tmp_path / 'concurrent.db'
    left = BarrierLedger(path, identity_registry=store)
    right = BarrierLedger(path, identity_registry=store)
    event_left = left.build_event(sport='football', entity_type='team', canonical_id=first.canonical_id, event_type='ALIAS_ADDED', effective_at=at(1), known_at=at(2), reason_code='LEFT', human_reviewed=False, previous_event_id=None, alias='Alias Left')
    event_right = right.build_event(sport='football', entity_type='team', canonical_id=first.canonical_id, event_type='ALIAS_ADDED', effective_at=at(1), known_at=at(3), reason_code='RIGHT', human_reviewed=False, previous_event_id=None, alias='Alias Right')
    accepted, rejected = [], []
    lock = threading.Lock()
    def worker(ledger, event):
        try:
            stored = ledger.append(event)
            with lock: accepted.append(stored.event_id)
        except Exception as error:
            with lock: rejected.append(str(error))
    threads = [
        threading.Thread(target=worker, name='matrix-v7r-chain-1', args=(left, event_left)),
        threading.Thread(target=worker, name='matrix-v7r-chain-2', args=(right, event_right)),
    ]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert 'IDENTITY_LIFECYCLE_NON_LINEAR_CHAIN' in rejected[0]
    assert SQLiteCanonicalIdentityLifecycleLedger(path, identity_registry=store).audit_integrity().ok is True

def test_concurrent_supersession_cycle_is_transactionally_rejected(tmp_path):
    store, first, second = registry(tmp_path, 'CYCLE')
    class BarrierLedger(SQLiteCanonicalIdentityLifecycleLedger):
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        waiters = 0
        def _events_for(self, canonical_id):
            events = super()._events_for(canonical_id)
            if threading.current_thread().name.startswith('matrix-v7r-cycle-'):
                wait = False
                with self.lock:
                    if self.waiters < 2:
                        self.waiters += 1
                        wait = True
                if wait:
                    self.barrier.wait(timeout=15)
            return events
    path = tmp_path / 'cycle.db'
    left = BarrierLedger(path, identity_registry=store)
    right = BarrierLedger(path, identity_registry=store)
    event_left = left.build_event(sport='football', entity_type='team', canonical_id=first.canonical_id, event_type='SUPERSEDED', effective_at=at(10), known_at=at(12), reason_code='A_TO_B', human_reviewed=True, previous_event_id=None, superseded_by_canonical_id=second.canonical_id)
    event_right = right.build_event(sport='football', entity_type='team', canonical_id=second.canonical_id, event_type='SUPERSEDED', effective_at=at(10), known_at=at(12), reason_code='B_TO_A', human_reviewed=True, previous_event_id=None, superseded_by_canonical_id=first.canonical_id)
    accepted, rejected = [], []
    lock = threading.Lock()
    def worker(ledger, event):
        try:
            stored = ledger.append(event)
            with lock: accepted.append(stored.event_id)
        except Exception as error:
            with lock: rejected.append(str(error))
    threads = [
        threading.Thread(target=worker, name='matrix-v7r-cycle-1', args=(left, event_left)),
        threading.Thread(target=worker, name='matrix-v7r-cycle-2', args=(right, event_right)),
    ]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert 'IDENTITY_SUPERSESSION_CYCLE' in rejected[0]
    assert SQLiteCanonicalIdentityLifecycleLedger(path, identity_registry=store).audit_integrity().ok is True
