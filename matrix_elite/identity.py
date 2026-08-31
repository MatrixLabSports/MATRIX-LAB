from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Iterable, Mapping


def _sha(value: str, name: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{name}_REQUIRED")
    int(value, 16)
    return value.lower()


@dataclass(frozen=True)
class IdentityBinding:
    provider: str
    provider_entity_id: str
    canonical_entity_id: str
    confidence: float
    evidence_sha256: str
    status: str = "CONFIRMED"
    entity_type: str = "UNKNOWN"
    available_at: datetime | None = None

    def __post_init__(self):
        if not self.provider.strip() or not self.provider_entity_id.strip() or not self.canonical_entity_id.strip():
            raise ValueError("IDENTITY_KEY_REQUIRED")
        if not self.entity_type.strip():
            raise ValueError("ENTITY_TYPE_REQUIRED")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("IDENTITY_CONFIDENCE_OUT_OF_RANGE")
        _sha(self.evidence_sha256, "IDENTITY_EVIDENCE_SHA256")
        if self.status not in {"CONFIRMED", "QUARANTINED", "REVIEW_REQUIRED"}:
            raise ValueError("IDENTITY_STATUS_INVALID")
        if self.available_at is not None and (self.available_at.tzinfo is None or self.available_at.utcoffset() is None):
            raise ValueError("IDENTITY_AVAILABLE_AT_MUST_BE_AWARE")


@dataclass(frozen=True)
class IdentityGovernanceEvent:
    event_id: str
    action: str
    canonical_entity_ids: tuple[str, ...]
    provider_keys: tuple[tuple[str, str], ...]
    approved_by: str
    approved_at: datetime
    evidence_sha256: str
    reason: str

    def __post_init__(self) -> None:
        if self.action not in {"MERGE", "SPLIT", "QUARANTINE", "UNQUARANTINE"}:
            raise ValueError("IDENTITY_GOVERNANCE_ACTION_INVALID")
        if not self.event_id.strip() or not self.approved_by.strip() or not self.reason.strip():
            raise ValueError("IDENTITY_GOVERNANCE_METADATA_REQUIRED")
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise ValueError("IDENTITY_GOVERNANCE_TIME_MUST_BE_AWARE")
        _sha(self.evidence_sha256, "IDENTITY_GOVERNANCE_EVIDENCE_SHA256")


class CanonicalIdentityRegistry:
    """Provider crosswalk with explicit conflict quarantine and governed rebinding."""

    def __init__(self):
        self._bindings: dict[tuple[str, str], IdentityBinding] = {}
        self._history: dict[tuple[str, str], list[IdentityBinding]] = {}
        self._canonical_types: dict[str, str] = {}
        self._quarantined_provider_keys: set[tuple[str, str]] = set()
        self._quarantined_canonical_ids: set[str] = set()
        self._events: list[IdentityGovernanceEvent] = []

    def bind(self, binding: IdentityBinding) -> None:
        key = (binding.provider, binding.provider_entity_id)
        canonical_type = self._canonical_types.get(binding.canonical_entity_id)
        if canonical_type is not None and canonical_type != binding.entity_type:
            self._quarantined_provider_keys.add(key)
            self._quarantined_canonical_ids.add(binding.canonical_entity_id)
            raise ValueError("CANONICAL_ENTITY_TYPE_CONFLICT")
        prior = self._bindings.get(key)
        if prior and prior.canonical_entity_id != binding.canonical_entity_id:
            self._quarantined_provider_keys.add(key)
            raise ValueError("IDENTITY_REBIND_REQUIRES_EXPLICIT_MERGE_SPLIT_GOVERNANCE")
        if binding.status == "QUARANTINED":
            self._quarantined_provider_keys.add(key)
        self._canonical_types[binding.canonical_entity_id] = binding.entity_type
        self._bindings[key] = binding
        versions = self._history.setdefault(key, [])
        if not versions or versions[-1] != binding:
            versions.append(binding)

    def resolve(
        self,
        provider: str,
        provider_entity_id: str,
        *,
        minimum_confidence: float = 0.95,
        as_of: datetime | None = None,
    ) -> str:
        key = (provider, provider_entity_id)
        if as_of is not None and (as_of.tzinfo is None or as_of.utcoffset() is None):
            raise ValueError("IDENTITY_AS_OF_MUST_BE_AWARE")
        if as_of is None:
            b = self._bindings.get(key)
        else:
            versions = self._history.get(key, ())
            eligible = [v for v in versions if v.available_at is None or v.available_at <= as_of]
            b = eligible[-1] if eligible else None
        if b is None:
            raise KeyError("IDENTITY_NOT_FOUND_AS_OF" if as_of is not None else "IDENTITY_NOT_FOUND")
        # Current conflict quarantine is intentionally retrospective/fail-safe until
        # explicit governance resolves the ambiguity.
        if key in self._quarantined_provider_keys:
            raise ValueError("IDENTITY_QUARANTINED")
        if as_of is None and b.canonical_entity_id in self._quarantined_canonical_ids:
            raise ValueError("IDENTITY_QUARANTINED")
        if b.status != "CONFIRMED" or b.confidence < minimum_confidence:
            raise ValueError("IDENTITY_NOT_ADMISSIBLE")
        return b.canonical_entity_id

    def resolve_by_name(self, *_args, **_kwargs):
        raise ValueError("SILENT_NAME_JOIN_FORBIDDEN")

    def quarantine(
        self,
        *,
        provider_keys: Iterable[tuple[str, str]] = (),
        canonical_entity_ids: Iterable[str] = (),
        event: IdentityGovernanceEvent,
    ) -> None:
        if event.action != "QUARANTINE":
            raise ValueError("QUARANTINE_EVENT_REQUIRED")
        keys = set(provider_keys)
        canonical = set(canonical_entity_ids)
        if not keys and not canonical:
            raise ValueError("QUARANTINE_TARGET_REQUIRED")
        if set(event.provider_keys) != keys or set(event.canonical_entity_ids) != canonical:
            raise ValueError("QUARANTINE_EVENT_TARGET_MISMATCH")
        self._quarantined_provider_keys.update(keys)
        self._quarantined_canonical_ids.update(canonical)
        self._events.append(event)

    def merge(self, *, source_ids: Iterable[str], target_id: str, event: IdentityGovernanceEvent) -> None:
        sources = tuple(sorted(set(source_ids)))
        if event.action != "MERGE" or not sources or not target_id.strip() or target_id in sources:
            raise ValueError("MERGE_GOVERNANCE_INVALID")
        affected = [k for k, b in self._bindings.items() if b.canonical_entity_id in sources]
        if not affected:
            raise ValueError("MERGE_SOURCE_NOT_FOUND")
        if set(event.provider_keys) != set(affected) or set(event.canonical_entity_ids) != set(sources) | {target_id}:
            raise ValueError("MERGE_EVENT_TARGET_MISMATCH")
        entity_types = {self._bindings[k].entity_type for k in affected}
        if len(entity_types) != 1:
            raise ValueError("MERGE_ENTITY_TYPE_CONFLICT")
        target_type = next(iter(entity_types))
        existing_target_type = self._canonical_types.get(target_id)
        if existing_target_type is not None and existing_target_type != target_type:
            raise ValueError("MERGE_TARGET_ENTITY_TYPE_CONFLICT")
        for key in affected:
            prior = self._bindings[key]
            self._bindings[key] = IdentityBinding(
                provider=prior.provider,
                provider_entity_id=prior.provider_entity_id,
                canonical_entity_id=target_id,
                confidence=prior.confidence,
                evidence_sha256=event.evidence_sha256,
                status="CONFIRMED",
                entity_type=prior.entity_type,
                available_at=event.approved_at,
            )
            self._history.setdefault(key, []).append(self._bindings[key])
            self._quarantined_provider_keys.discard(key)
        self._canonical_types[target_id] = target_type
        self._quarantined_canonical_ids.update(sources)
        self._events.append(event)

    def split(
        self,
        *,
        source_id: str,
        assignments: Mapping[tuple[str, str], str],
        event: IdentityGovernanceEvent,
    ) -> None:
        if event.action != "SPLIT" or not source_id.strip():
            raise ValueError("SPLIT_GOVERNANCE_INVALID")
        source_keys = {k for k, b in self._bindings.items() if b.canonical_entity_id == source_id}
        if not source_keys or set(assignments) != source_keys:
            raise ValueError("SPLIT_ASSIGNMENTS_MUST_COVER_SOURCE_EXACTLY")
        if len(set(assignments.values())) < 2:
            raise ValueError("SPLIT_REQUIRES_MULTIPLE_TARGETS")
        if set(event.provider_keys) != source_keys or set(event.canonical_entity_ids) != {source_id} | set(assignments.values()):
            raise ValueError("SPLIT_EVENT_TARGET_MISMATCH")
        source_type = self._canonical_types.get(source_id)
        if source_type is None:
            raise ValueError("SPLIT_SOURCE_TYPE_NOT_FOUND")
        for key, target_id in assignments.items():
            if not target_id.strip():
                raise ValueError("SPLIT_TARGET_REQUIRED")
            existing_target_type = self._canonical_types.get(target_id)
            if existing_target_type is not None and existing_target_type != source_type:
                raise ValueError("SPLIT_TARGET_ENTITY_TYPE_CONFLICT")
            prior = self._bindings[key]
            self._bindings[key] = IdentityBinding(
                provider=prior.provider,
                provider_entity_id=prior.provider_entity_id,
                canonical_entity_id=target_id,
                confidence=prior.confidence,
                evidence_sha256=event.evidence_sha256,
                status="CONFIRMED",
                entity_type=prior.entity_type,
                available_at=event.approved_at,
            )
            self._history.setdefault(key, []).append(self._bindings[key])
            self._canonical_types[target_id] = source_type
            self._quarantined_provider_keys.discard(key)
        self._quarantined_canonical_ids.add(source_id)
        self._events.append(event)

    def crosswalk_coverage(self, expected_provider_keys: Iterable[tuple[str, str]]) -> dict[str, int | float]:
        expected = set(expected_provider_keys)
        resolved = 0
        quarantined = 0
        missing = 0
        for key in expected:
            if key not in self._bindings:
                missing += 1
            elif key in self._quarantined_provider_keys or self._bindings[key].canonical_entity_id in self._quarantined_canonical_ids:
                quarantined += 1
            elif self._bindings[key].status == "CONFIRMED":
                resolved += 1
            else:
                quarantined += 1
        total = len(expected)
        return {
            "total": total,
            "resolved": resolved,
            "quarantined_or_review": quarantined,
            "missing": missing,
            "resolved_rate": (resolved / total) if total else 1.0,
        }

    def audit(self) -> tuple[str, ...]:
        findings: list[str] = []
        for key, binding in self._bindings.items():
            if binding.status == "CONFIRMED" and key in self._quarantined_provider_keys:
                findings.append(f"CONFIRMED_BUT_PROVIDER_KEY_QUARANTINED:{key[0]}:{key[1]}")
            if binding.status == "CONFIRMED" and binding.canonical_entity_id in self._quarantined_canonical_ids:
                findings.append(f"CONFIRMED_BUT_CANONICAL_ID_QUARANTINED:{binding.canonical_entity_id}")
        return tuple(sorted(set(findings)))

    def manifest_sha256(self) -> str:
        rows = []
        for key in sorted(self._history):
            for version_index, b in enumerate(self._history[key], start=1):
                rows.append({
                    "provider": b.provider,
                    "provider_entity_id": b.provider_entity_id,
                    "version_index": version_index,
                    "canonical_entity_id": b.canonical_entity_id,
                    "entity_type": b.entity_type,
                    "confidence": float(b.confidence),
                    "status": b.status,
                    "available_at": b.available_at.isoformat() if b.available_at else None,
                    "evidence_sha256": b.evidence_sha256,
                    "current": self._bindings.get(key) == b,
                    "quarantined_provider_key": key in self._quarantined_provider_keys,
                    "quarantined_canonical_id": b.canonical_entity_id in self._quarantined_canonical_ids,
                })
        raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return sha256(raw).hexdigest()

    @property
    def governance_event_count(self) -> int:
        return len(self._events)
