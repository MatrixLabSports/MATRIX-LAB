from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Iterable


_SENSITIVE_NAMES = {
    "api_key",
    "apikey",
    "x_api_key",
    "access_token",
    "refresh_token",
    "auth_token",
    "x_auth_token",
    "token",
    "client_secret",
    "password",
    "passwd",
    "secret",
    "private_key",
}

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
    "super-secret",
    "secret-value",
    "synthetic",
    "fixture",
)

_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    \b(
        api[_-]?key
        |access[_-]?token
        |refresh[_-]?token
        |auth[_-]?token
        |client[_-]?secret
        |password
        |passwd
        |private[_-]?key
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
        |refresh[_-]?token
        |auth[_-]?token
        |client[_-]?secret
        |password
        |passwd
        |private[_-]?key
    )
    ["']?
    \s*:\s*
    ["']
    ([^"']{12,})
    ["']
    """
)

_PEM_BLOCK_PATTERN = re.compile(
    r"""(?sx)
    -----BEGIN\s+
    (?:RSA\s+|EC\s+|OPENSSH\s+)?
    PRIVATE\s+KEY-----
    \s*
    [A-Za-z0-9+/=\r\n]{80,}
    \s*
    -----END\s+
    (?:RSA\s+|EC\s+|OPENSSH\s+)?
    PRIVATE\s+KEY-----
    """
)

_HIGH_CONFIDENCE_PATTERNS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
)

_TEXT_SUFFIXES = {
    ".py",
    ".ps1",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".pem",
    ".key",
    ".crt",
}

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

    return tuple(root / value for value in values)


def _looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(
        term in lowered
        for term in _PLACEHOLDER_TERMS
    )


def _normalized_name(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("-", "_")
    )


def _sensitive_name(value: str) -> bool:
    normalized = _normalized_name(value)

    return (
        normalized in _SENSITIVE_NAMES
        or normalized.endswith("_api_key")
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
        or normalized.endswith("_private_key")
    )


def _high_confidence_leak(text: str) -> bool:
    if _PEM_BLOCK_PATTERN.search(text):
        return True

    return any(
        pattern.search(text)
        for pattern in _HIGH_CONFIDENCE_PATTERNS
    )


def _literal_secret(
    value: ast.expr | None,
) -> bool:
    if not (
        isinstance(value, ast.Constant)
        and isinstance(value.value, str)
    ):
        return False

    text = value.value

    if _is_placeholder(text):
        return False

    if _high_confidence_leak(text):
        return True

    return len(text) >= 12


def _python_has_hardcoded_secret(
    text: str,
) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        match = _ASSIGNMENT_PATTERN.search(text)
        return (
            match is not None
            and not _is_placeholder(match.group(2))
        )

    def target_is_sensitive(
        target: ast.expr,
    ) -> bool:
        if isinstance(target, ast.Name):
            return _sensitive_name(target.id)

        if isinstance(target, ast.Attribute):
            return _sensitive_name(target.attr)

        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if (
                _literal_secret(node.value)
                and any(
                    target_is_sensitive(target)
                    for target in node.targets
                )
            ):
                return True

        elif isinstance(node, ast.AnnAssign):
            if (
                target_is_sensitive(node.target)
                and _literal_secret(node.value)
            ):
                return True

        elif isinstance(node, ast.Dict):
            for key, value in zip(
                node.keys,
                node.values,
            ):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and _sensitive_name(key.value)
                    and _literal_secret(value)
                ):
                    return True

        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if (
                    keyword.arg is not None
                    and _sensitive_name(keyword.arg)
                    and _literal_secret(keyword.value)
                ):
                    return True

    return False


def _non_python_has_hardcoded_secret(
    text: str,
) -> bool:
    if _high_confidence_leak(text):
        return True

    assignment = _ASSIGNMENT_PATTERN.search(text)

    if (
        assignment is not None
        and not _is_placeholder(
            assignment.group(2)
        )
    ):
        return True

    colon = _COLON_PATTERN.search(text)

    if (
        colon is not None
        and not _is_placeholder(
            colon.group(2)
        )
    ):
        return True

    return False


def _fixture_path(relative: str) -> bool:
    return relative.startswith(
        (
            "tests/",
            "docs/",
        )
    )


def _forbidden_name(
    path: Path,
    forbidden_names: set[str],
) -> bool:
    name = path.name.lower()

    if name in forbidden_names:
        return True

    # .env.production / .env.test / .env.local etc.
    return name.startswith(".env.")


def _looks_text_by_name(path: Path) -> bool:
    return (
        path.suffix.lower() in _TEXT_SUFFIXES
        or path.name.lower().startswith(".env")
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

        if _forbidden_name(
            path,
            forbidden,
        ):
            findings.append(
                SecretScanFinding(
                    path=relative,
                    rule="FORBIDDEN_TRACKED_NAME",
                )
            )

        if not path.is_file():
            continue

        try:
            size = path.stat().st_size
        except OSError:
            findings.append(
                SecretScanFinding(
                    path=relative,
                    rule="UNREADABLE_TRACKED_FILE",
                )
            )
            continue

        if (
            size > _MAX_SCAN_BYTES
            and _looks_text_by_name(path)
        ):
            findings.append(
                SecretScanFinding(
                    path=relative,
                    rule="OVERSIZED_TEXT_NOT_SCANNED",
                )
            )
            continue

        if size > _MAX_SCAN_BYTES:
            continue

        try:
            data = path.read_bytes()
        except OSError:
            findings.append(
                SecretScanFinding(
                    path=relative,
                    rule="UNREADABLE_TRACKED_FILE",
                )
            )
            continue

        if _looks_binary(data):
            continue

        text = data.decode(
            "utf-8-sig",
            errors="ignore",
        )
        scanned += 1

        if _fixture_path(relative):
            leaked = _high_confidence_leak(
                text
            )
        elif path.suffix.lower() == ".py":
            leaked = _python_has_hardcoded_secret(
                text
            )
        else:
            leaked = _non_python_has_hardcoded_secret(
                text
            )

        if leaked:
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
