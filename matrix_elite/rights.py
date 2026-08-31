from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


def _sha(value: str) -> None:
    if len(value) != 64:
        raise ValueError("RIGHTS_EVIDENCE_SHA256_REQUIRED")
    int(value, 16)


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")
    return value


@dataclass(frozen=True)
class RightsProfile:
    provider: str
    research: bool
    retention: bool
    derivatives: bool
    model_training: bool
    display: bool
    redistribution: bool
    commercial_use: bool
    expires_at: datetime | str | None
    evidence_sha256: str
    effective_from: datetime | None = None
    terminated_at: datetime | None = None
    termination_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("RIGHTS_PROVIDER_REQUIRED")
        _sha(self.evidence_sha256)
        if isinstance(self.expires_at, datetime):
            _aware(self.expires_at, "RIGHTS_EXPIRES_AT")
        elif self.expires_at is not None and not isinstance(self.expires_at, str):
            raise ValueError("RIGHTS_EXPIRES_AT_INVALID")
        if isinstance(self.expires_at, str) and self.expires_at:
            # Backward-compatible with R1 while forcing timezone semantics when parseable.
            parsed = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            _aware(parsed, "RIGHTS_EXPIRES_AT")
        if self.effective_from is not None:
            _aware(self.effective_from, "RIGHTS_EFFECTIVE_FROM")
        if self.terminated_at is not None:
            _aware(self.terminated_at, "RIGHTS_TERMINATED_AT")
            if not self.termination_reason:
                raise ValueError("RIGHTS_TERMINATION_REASON_REQUIRED")

    def _expiry(self) -> datetime | None:
        if self.expires_at is None:
            return None
        if isinstance(self.expires_at, datetime):
            return self.expires_at
        return datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))

    def active_at(self, at: datetime) -> bool:
        at = _aware(at, "RIGHTS_AT")
        if self.effective_from is not None and at < self.effective_from:
            return False
        expiry = self._expiry()
        if expiry is not None and at >= expiry:
            return False
        if self.terminated_at is not None and at >= self.terminated_at:
            return False
        return True

    def admissible_for(self, purpose: str, *, at: datetime | None = None) -> bool:
        mapping = {
            "research": self.research,
            "retention": self.retention,
            "derivatives": self.derivatives,
            "model_training": self.model_training,
            "display": self.display,
            "redistribution": self.redistribution,
            "commercial_use": self.commercial_use,
        }
        if purpose not in mapping:
            raise ValueError("RIGHTS_PURPOSE_UNKNOWN")
        if at is not None and not self.active_at(at):
            return False
        return bool(mapping[purpose])


class RightsRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, RightsProfile] = {}
        self._history: dict[str, list[RightsProfile]] = {}

    def register(self, profile: RightsProfile, *, supersedes_evidence_sha256: str | None = None) -> None:
        prior = self._profiles.get(profile.provider)
        if prior is not None:
            if prior.evidence_sha256 == profile.evidence_sha256:
                if prior != profile:
                    raise ValueError("RIGHTS_EVIDENCE_REUSED_FOR_DIFFERENT_PROFILE")
                return
            if supersedes_evidence_sha256 != prior.evidence_sha256:
                raise ValueError("RIGHTS_PROFILE_REPLACEMENT_REQUIRES_VERSIONED_GOVERNANCE")
        self._profiles[profile.provider] = profile
        self._history.setdefault(profile.provider, []).append(profile)

    def history(self, provider: str) -> tuple[RightsProfile, ...]:
        return tuple(self._history.get(provider, ()))

    def get(self, provider: str) -> RightsProfile:
        try:
            return self._profiles[provider]
        except KeyError as exc:
            raise KeyError("RIGHTS_PROFILE_NOT_FOUND") from exc

    def profile_at(self, provider: str, at: datetime) -> RightsProfile:
        at = _aware(at, "RIGHTS_AT")
        versions = self._history.get(provider, ())
        eligible = [p for p in versions if p.effective_from is None or p.effective_from <= at]
        if not eligible:
            raise KeyError("RIGHTS_PROFILE_NOT_FOUND_AS_OF")
        return eligible[-1]

    def audit_use(
        self,
        *,
        providers: Iterable[str],
        purposes: Iterable[str],
        at: datetime,
    ) -> dict[str, object]:
        at = _aware(at, "RIGHTS_AUDIT_AT")
        provider_set = sorted(set(providers))
        purpose_set = tuple(sorted(set(purposes)))
        failures: list[dict[str, str]] = []
        for provider in provider_set:
            try:
                profile = self.profile_at(provider, at)
            except KeyError:
                failures.append({"provider": provider, "code": "RIGHTS_PROFILE_NOT_FOUND"})
                continue
            if not profile.active_at(at):
                failures.append({"provider": provider, "code": "RIGHTS_PROFILE_INACTIVE"})
                continue
            for purpose in purpose_set:
                if not profile.admissible_for(purpose, at=at):
                    failures.append({"provider": provider, "code": f"RIGHTS_PURPOSE_FORBIDDEN:{purpose}"})
        return {
            "providers": provider_set,
            "purposes": purpose_set,
            "at": at.isoformat(),
            "pass": not failures,
            "failures": failures,
        }

    def require_use(self, *, providers: Iterable[str], purposes: Iterable[str], at: datetime) -> None:
        result = self.audit_use(providers=providers, purposes=purposes, at=at)
        if not result["pass"]:
            codes = ",".join(sorted({f["code"] for f in result["failures"]}))
            raise ValueError("RIGHTS_GATE_FAILED:" + codes)
