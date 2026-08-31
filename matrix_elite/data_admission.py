from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from .identity import CanonicalIdentityRegistry
from .pit import PITRecord, audit_revision_graph, snapshot_as_of, snapshot_manifest
from .rights import RightsRegistry


@dataclass(frozen=True)
class DataAdmissionResult:
    admitted: bool
    codes: tuple[str, ...]
    snapshot_sha256: str | None
    record_count: int


def admit_training_snapshot(
    records: Sequence[PITRecord],
    *,
    as_of: datetime,
    identity_registry: CanonicalIdentityRegistry,
    identity_keys: Iterable[tuple[str, str]],
    rights_registry: RightsRegistry,
    required_rights: tuple[str, ...] = ("research", "retention", "derivatives", "model_training"),
    minimum_identity_confidence: float = 0.95,
) -> DataAdmissionResult:
    """Fail closed across PIT + identity + rights before model training."""
    codes: list[str] = []
    graph = audit_revision_graph(records)
    if graph:
        codes.extend(sorted({"PIT:" + v.code for v in graph}))

    try:
        snapshot = snapshot_as_of(records, as_of=as_of)
    except ValueError as exc:
        codes.append(str(exc))
        snapshot = ()

    for provider, provider_entity_id in identity_keys:
        try:
            identity_registry.resolve(
                provider,
                provider_entity_id,
                minimum_confidence=minimum_identity_confidence,
                as_of=as_of,
            )
        except (KeyError, ValueError) as exc:
            codes.append("IDENTITY:" + str(exc))

    rights = rights_registry.audit_use(
        providers={r.provider for r in snapshot},
        purposes=required_rights,
        at=as_of,
    )
    if not rights["pass"]:
        codes.extend("RIGHTS:" + f["code"] for f in rights["failures"])

    unique = tuple(sorted(set(codes)))
    if unique:
        return DataAdmissionResult(False, unique, None, len(snapshot))
    manifest = snapshot_manifest(records, as_of=as_of)
    return DataAdmissionResult(True, (), manifest.snapshot_sha256, manifest.record_count)
