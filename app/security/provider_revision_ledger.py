from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Iterator

from app.release.canonical import canonical_json
from app.security.provider_temporal_truth import ProviderTruthVersion

GENESIS = "0" * 64


def _payload(value: ProviderTruthVersion) -> dict[str, object]:
    return json.loads(canonical_json(value))


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@contextmanager
def _exclusive_lock(lock_path: Path) -> Iterator[None]:
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


class ProviderRevisionLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, version: ProviderTruthVersion) -> str:
        with _exclusive_lock(self.lock_path):
            ok, _, previous, version_ids = verify_provider_revision_ledger(self.path)
            if not ok:
                raise RuntimeError("provider revision ledger integrity failure")
            if version.version_id in version_ids:
                raise RuntimeError("provider revision ledger duplicate version_id")
            payload = _payload(version)
            digest = sha256(previous.encode("ascii") + _canonical_bytes(payload)).hexdigest()
            row = {"previous_hash": previous, "payload": payload, "hash": digest}
            with self.path.open("ab", buffering=0) as handle:
                handle.write(_canonical_bytes(row) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            return digest


def verify_provider_revision_ledger(path: str | Path) -> tuple[bool, int, str, tuple[str, ...]]:
    ledger_path = Path(path)
    if not ledger_path.exists():
        return True, 0, GENESIS, ()
    previous = GENESIS
    count = 0
    version_ids: list[str] = []
    try:
        with ledger_path.open("rb") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                row = json.loads(raw)
                if row.get("previous_hash") != previous:
                    return False, count, previous, tuple(version_ids)
                payload = row["payload"]
                expected = sha256(previous.encode("ascii") + _canonical_bytes(payload)).hexdigest()
                if row.get("hash") != expected:
                    return False, count, previous, tuple(version_ids)
                version_id = payload.get("version_id")
                if not isinstance(version_id, str) or not version_id or version_id in version_ids:
                    return False, count, previous, tuple(version_ids)
                version_ids.append(version_id)
                previous = expected
                count += 1
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False, count, previous, tuple(version_ids)
    return True, count, previous, tuple(version_ids)
