from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Mapping

_SECRET_NAME = re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key)")
_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|private[_-]?key)\b\s*[:=]\s*[\"']([^\"']+)[\"']"
)
_URI_CREDS = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s:/]+:[^\s@/]+@")
_PEM = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_PLACEHOLDERS = {"changeme", "example", "placeholder", "dummy", "test", "<secret>", "${secret}"}


@dataclass(frozen=True)
class SecretFinding:
    line: int
    kind: str
    name: str


def scan_text(text: str) -> tuple[SecretFinding, ...]:
    findings: list[SecretFinding] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if _PEM.search(line):
            findings.append(SecretFinding(line_no, "PRIVATE_KEY", "private_key"))
        if _URI_CREDS.search(line):
            findings.append(SecretFinding(line_no, "URI_CREDENTIALS", "uri_credentials"))
        for match in _ASSIGNMENT.finditer(line):
            value = match.group(2).strip()
            if value.casefold() in _PLACEHOLDERS or value.startswith("${") or value.startswith("ENV["):
                continue
            if len(value) >= 8:
                findings.append(SecretFinding(line_no, "HARDCODED_SECRET", match.group(1)))
    return tuple(findings)


@dataclass(frozen=True)
class EnvironmentSecretRef:
    variable_name: str
    min_length: int = 16

    def __post_init__(self) -> None:
        if not self.variable_name or not self.variable_name.replace("_", "A").isalnum():
            raise ValueError("invalid environment variable name")
        if self.min_length < 8:
            raise ValueError("min_length too small for secret policy")
        if not _SECRET_NAME.search(self.variable_name):
            raise ValueError("environment secret variable should be explicitly named")

    def resolve(self, environ: Mapping[str, str] | None = None) -> str:
        env = os.environ if environ is None else environ
        value = env.get(self.variable_name)
        if value is None:
            raise RuntimeError(f"missing secret: {self.variable_name}")
        if len(value) < self.min_length:
            raise RuntimeError(f"secret too short: {self.variable_name}")
        return value
