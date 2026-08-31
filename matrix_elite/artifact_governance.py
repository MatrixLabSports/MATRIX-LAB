from __future__ import annotations

from dataclasses import dataclass


def _sha(value: str) -> None:
    if len(value) != 64:
        raise ValueError("ARTIFACT_SHA256_REQUIRED")
    int(value, 16)


@dataclass(frozen=True)
class ArtifactRecord:
    role: str
    filename: str
    sha256: str
    status: str
    supersedes_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.role.strip() or not self.filename.strip():
            raise ValueError("ARTIFACT_METADATA_REQUIRED")
        _sha(self.sha256)
        if self.status not in {"ACTIVE", "SUPERSEDED", "QUARANTINED"}:
            raise ValueError("ARTIFACT_STATUS_INVALID")
        if self.supersedes_sha256 is not None:
            _sha(self.supersedes_sha256)


class ActiveArtifactCatalog:
    """Resolve execution artifacts by role + exact SHA, never by highest version name."""

    def __init__(self) -> None:
        self._records: list[ArtifactRecord] = []
        self._active: dict[str, ArtifactRecord] = {}

    def add_initial(self, record: ArtifactRecord) -> None:
        if record.status != "ACTIVE":
            raise ValueError("INITIAL_ARTIFACT_MUST_BE_ACTIVE")
        if record.role in self._active:
            raise ValueError("ACTIVE_ARTIFACT_ALREADY_EXISTS")
        self._records.append(record); self._active[record.role] = record

    def promote(self, record: ArtifactRecord) -> None:
        if record.status != "ACTIVE":
            raise ValueError("PROMOTED_ARTIFACT_MUST_BE_ACTIVE")
        prior = self._active.get(record.role)
        if prior is None:
            raise ValueError("NO_ACTIVE_ARTIFACT_TO_SUPERSEDE")
        if record.supersedes_sha256 != prior.sha256:
            raise ValueError("ARTIFACT_SUPERSESSION_HASH_MISMATCH")
        superseded = ArtifactRecord(prior.role, prior.filename, prior.sha256, "SUPERSEDED", prior.supersedes_sha256)
        self._records.append(superseded)
        self._records.append(record)
        self._active[record.role] = record

    def quarantine_active(self, role: str) -> None:
        prior = self._active.pop(role, None)
        if prior is None:
            raise KeyError("ACTIVE_ARTIFACT_NOT_FOUND")
        self._records.append(ArtifactRecord(prior.role, prior.filename, prior.sha256, "QUARANTINED", prior.supersedes_sha256))

    def resolve_active(self, role: str) -> ArtifactRecord:
        try:
            return self._active[role]
        except KeyError as exc:
            raise KeyError("ACTIVE_ARTIFACT_NOT_FOUND") from exc

    def resolve_by_highest_version_name(self, *_args, **_kwargs):
        raise ValueError("VERSION_NAME_BASED_EXECUTION_SELECTION_FORBIDDEN")

    def audit(self) -> dict[str, object]:
        return {
            "active_roles": tuple(sorted(self._active)),
            "active_count": len(self._active),
            "record_count": len(self._records),
            "one_active_per_role": len(self._active) == len(set(self._active)),
        }
