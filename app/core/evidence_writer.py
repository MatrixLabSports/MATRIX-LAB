from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


_FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {
        "api_key",
        "api_football_key",
        "password",
        "pgpassword",
        "database_url",
        "matrix_database_url",
        "matrix_restore_database_url",
        "authorization",
        "access_token",
        "refresh_token",
        "secret",
    }
)


def _assert_no_secret_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_EVIDENCE_KEYS:
                raise ValueError(f"evidence payload contains forbidden key at {path}.{key}")
            _assert_no_secret_keys(nested, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_no_secret_keys(nested, path=f"{path}[{index}]")


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_sha256_path(path: str | Path) -> Path:
    target = Path(path)
    return target.with_name(target.name + ".sha256")


def verify_evidence_sha256(path: str | Path) -> bool:
    target = Path(path)
    sidecar = evidence_sha256_path(target)
    if not target.is_file() or not sidecar.is_file():
        return False
    expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    return len(expected) == 64 and expected == file_sha256(target)


def write_json_evidence(
    evidence_dir: str | Path,
    *,
    prefix: str,
    payload: Mapping[str, Any],
    observed_at_utc: datetime | None = None,
) -> Path:
    """Atomically write sanitized JSON gate evidence plus a SHA-256 sidecar.

    Credential-bearing key names are rejected recursively.  Both the JSON and its
    digest sidecar are written through temporary files and atomically replaced.
    Callers still remain responsible for upstream data minimization.
    """

    if not isinstance(prefix, str) or not prefix.strip() or any(ch in prefix for ch in "/\\"):
        raise ValueError("evidence prefix must be a non-empty filename-safe segment")
    _assert_no_secret_keys(payload)

    now = observed_at_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None or now.utcoffset().total_seconds() != 0:
        raise ValueError("observed_at_utc must be timezone-aware UTC")

    directory = Path(evidence_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"{prefix}_{stamp}.json"
    temp = directory / f".{target.name}.tmp"
    document = dict(payload)
    document.setdefault("evidence_written_at_utc", now.isoformat())
    temp.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temp.replace(target)

    digest = file_sha256(target)
    sidecar = evidence_sha256_path(target)
    sidecar_temp = directory / f".{sidecar.name}.tmp"
    sidecar_temp.write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    sidecar_temp.replace(sidecar)
    return target
