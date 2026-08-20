from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Iterable


_PRIVATE_KEY_MARKERS = (
    "-----BEGIN " + "PRIVATE KEY-----",
    "-----BEGIN RSA " + "PRIVATE KEY-----",
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
    "-----BEGIN EC " + "PRIVATE KEY-----",
)

_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    \b(
        api[_-]?key
        |access[_-]?token
        |auth[_-]?token
        |client[_-]?secret
        |password
        |passwd
    )\b
    \s*=\s*
    ["']?
    ([A-Za-z0-9_./+=:@-]{12,})
    ["']?
    """
)

_COLON_PATTERN = re.compile(
    r"""(?ix)
    ["']?
    (
        api[_-]?key
        |access[_-]?token
        |auth[_-]?token
        |client[_-]?secret
        |password
        |passwd
    )
    ["']?
    \s*:\s*
    ["']
    ([^"']{12,})
    ["']
    """
)

_PLACEHOLDER_TERMS = (
    "example",
    "placeholder",
    "changeme",
    "dummy",
    "fake",
    "redacted",
    "runtime-only",
    "test-value",
    "not-a-secret",
)

_MAX_SCAN_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class SecretScanFinding:
    path: str
    rule: str


@dataclass(frozen=True)
class SecretScanReport:
    ok: bool
    scanned_files: int
    findings: tuple[SecretScanFinding, ...]


def _tracked_files(root: Path) -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )

    values = [
        item
        for item in completed.stdout.decode(
            "utf-8",
            errors="strict",
        ).split("\x00")
        if item
    ]

    return tuple(
        root / value
        for value in values
    )


def _looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(
        term in lowered
        for term in _PLACEHOLDER_TERMS
    )


def _read_text_candidate(
    path: Path,
) -> str | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None

    if size > _MAX_SCAN_BYTES:
        return None

    try:
        data = path.read_bytes()
    except OSError:
        return None

    if _looks_binary(data):
        return None

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return data.decode(
                "utf-8",
                errors="ignore",
            )


def scan_tracked_repository(
    root: str | Path,
    *,
    forbidden_names: Iterable[str],
) -> SecretScanReport:
    root_path = Path(root).resolve()
    forbidden = {
        str(value).lower()
        for value in forbidden_names
    }

    findings: list[SecretScanFinding] = []
    scanned = 0

    for path in _tracked_files(root_path):
        relative = path.relative_to(
            root_path
        ).as_posix()

        if path.name.lower() in forbidden:
            findings.append(
                SecretScanFinding(
                    path=relative,
                    rule="FORBIDDEN_TRACKED_NAME",
                )
            )

        if not path.is_file():
            continue

        text = _read_text_candidate(path)
        if text is None:
            continue

        scanned += 1

        if any(
            marker in text
            for marker in _PRIVATE_KEY_MARKERS
        ):
            findings.append(
                SecretScanFinding(
                    path=relative,
                    rule="PRIVATE_KEY_MATERIAL",
                )
            )
            continue

        assignment = _ASSIGNMENT_PATTERN.search(
            text
        )

        if (
            assignment is not None
            and not _is_placeholder(
                assignment.group(2)
            )
        ):
            findings.append(
                SecretScanFinding(
                    path=relative,
                    rule="LIKELY_EMBEDDED_SECRET",
                )
            )
            continue

        # JSON/YAML-style literals are checked outside test/docs
        # to reduce false positives from explicit security fixtures.
        if not relative.startswith(
            ("tests/", "docs/")
        ):
            colon = _COLON_PATTERN.search(
                text
            )

            if (
                colon is not None
                and not _is_placeholder(
                    colon.group(2)
                )
            ):
                findings.append(
                    SecretScanFinding(
                        path=relative,
                        rule="LIKELY_EMBEDDED_SECRET",
                    )
                )

    return SecretScanReport(
        ok=not findings,
        scanned_files=scanned,
        findings=tuple(findings),
    )
