from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Iterator

from .privacy_evidence_automation import PrivacyEvidenceSnapshot

GENESIS = "0" * 64


def _canonical(value: object) -> bytes:
    def default(obj: object):
        if hasattr(obj, "value"):
            return getattr(obj, "value")
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        raise TypeError(type(obj).__name__)
    return json.dumps(value, default=default, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


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


class PrivacyEvidenceLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, snapshot: PrivacyEvidenceSnapshot) -> str:
        with _exclusive_lock(self.lock_path):
            ok, _, previous = verify_privacy_evidence_ledger(self.path)
            if not ok:
                raise RuntimeError("privacy evidence ledger integrity failure")
            payload = asdict(snapshot)
            digest = sha256(previous.encode("ascii") + _canonical(payload)).hexdigest()
            row = {"previous_hash": previous, "payload": payload, "hash": digest}
            with self.path.open("ab", buffering=0) as handle:
                handle.write(_canonical(row) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            return digest


def verify_privacy_evidence_ledger(path: str | Path) -> tuple[bool, int, str]:
    p = Path(path)
    if not p.exists():
        return True, 0, GENESIS
    previous = GENESIS
    count = 0
    try:
        with p.open("rb") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                row = json.loads(raw)
                if row.get("previous_hash") != previous:
                    return False, count, previous
                payload = row["payload"]
                expected = sha256(previous.encode("ascii") + _canonical(payload)).hexdigest()
                if row.get("hash") != expected:
                    return False, count, previous
                previous = expected
                count += 1
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False, count, previous
    return True, count, previous
