from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable, Sequence

_ALLOWED_PARTITIONS = {"train", "validation", "test"}


def _parse_aware(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError("timestamp debe ser ISO-8601 válido") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp debe incluir zona horaria")
    return parsed.astimezone(timezone.utc)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class FootballResearchRow:
    """One leakage-safe observation for research/backtesting.

    `as_of_utc` is the information cutoff. Every feature in `features` must have been
    observable at or before that instant. Labels may describe the future outcome, but
    `label_observed_at_utc` must be strictly after the information cutoff.
    """

    fixture_id: str
    as_of_utc: str
    partition: str
    features: dict[str, int | float | str | bool | None]
    labels: dict[str, int | float | str | bool | None]
    label_observed_at_utc: str
    source_provider: str = "api_football"

    def __post_init__(self) -> None:
        if not isinstance(self.fixture_id, str) or not self.fixture_id.strip():
            raise ValueError("fixture_id no puede estar vacío")
        if self.partition not in _ALLOWED_PARTITIONS:
            raise ValueError("partition inválida")
        if not isinstance(self.features, dict) or not isinstance(self.labels, dict):
            raise ValueError("features y labels deben ser dict")
        if not self.features:
            raise ValueError("features no puede estar vacío")
        if not self.labels:
            raise ValueError("labels no puede estar vacío")
        as_of = _parse_aware(self.as_of_utc)
        label_at = _parse_aware(self.label_observed_at_utc)
        if label_at <= as_of:
            raise ValueError("label_observed_at_utc debe ser posterior a as_of_utc")
        if not isinstance(self.source_provider, str) or not self.source_provider.strip():
            raise ValueError("source_provider no puede estar vacío")


@dataclass(frozen=True)
class TemporalSplitPolicy:
    train_end_utc: str
    validation_end_utc: str
    test_end_utc: str | None = None

    def __post_init__(self) -> None:
        train_end = _parse_aware(self.train_end_utc)
        validation_end = _parse_aware(self.validation_end_utc)
        if validation_end <= train_end:
            raise ValueError("validation_end_utc debe ser posterior a train_end_utc")
        if self.test_end_utc is not None:
            test_end = _parse_aware(self.test_end_utc)
            if test_end <= validation_end:
                raise ValueError("test_end_utc debe ser posterior a validation_end_utc")

    def partition_for(self, as_of_utc: str) -> str:
        value = _parse_aware(as_of_utc)
        train_end = _parse_aware(self.train_end_utc)
        validation_end = _parse_aware(self.validation_end_utc)
        if value <= train_end:
            return "train"
        if value <= validation_end:
            return "validation"
        if self.test_end_utc is not None and value > _parse_aware(self.test_end_utc):
            raise ValueError("observación queda fuera del horizonte de test")
        return "test"


@dataclass(frozen=True)
class FootballDatasetManifest:
    dataset_name: str
    dataset_version: str
    created_at_utc: str
    row_count: int
    fixture_count: int
    partition_counts: dict[str, int]
    source_providers: tuple[str, ...]
    feature_names: tuple[str, ...]
    label_names: tuple[str, ...]
    data_sha256: str
    split_policy: dict[str, str | None]
    metadata: dict[str, int | float | str | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dataset_name.strip() or not self.dataset_version.strip():
            raise ValueError("dataset_name y dataset_version son obligatorios")
        _parse_aware(self.created_at_utc)
        if self.row_count < 0 or self.fixture_count < 0:
            raise ValueError("conteos del manifest no pueden ser negativos")
        if sum(self.partition_counts.values()) != self.row_count:
            raise ValueError("partition_counts no coincide con row_count")
        if len(self.data_sha256) != 64:
            raise ValueError("data_sha256 inválido")


class TemporalLeakageGuard:
    """Hard barriers against common leakage patterns in temporal sports datasets."""

    @staticmethod
    def validate_rows(rows: Sequence[FootballResearchRow]) -> None:
        seen_keys: set[tuple[str, str]] = set()
        fixture_partitions: dict[str, set[str]] = {}
        for row in rows:
            key = (row.fixture_id, row.as_of_utc)
            if key in seen_keys:
                raise ValueError(f"observación duplicada: {row.fixture_id} @ {row.as_of_utc}")
            seen_keys.add(key)
            fixture_partitions.setdefault(row.fixture_id, set()).add(row.partition)
            as_of = _parse_aware(row.as_of_utc)
            label_at = _parse_aware(row.label_observed_at_utc)
            if label_at <= as_of:
                raise ValueError("fuga temporal: label disponible antes/durante el corte")
        # A fixture may have multiple live observations, but assigning one fixture to
        # multiple dataset partitions leaks match-specific information across splits.
        leaked = {fixture: parts for fixture, parts in fixture_partitions.items() if len(parts) > 1}
        if leaked:
            raise ValueError(f"fixture presente en múltiples particiones: {sorted(leaked)}")

    @staticmethod
    def validate_partition_order(rows: Sequence[FootballResearchRow]) -> None:
        by_partition: dict[str, list[datetime]] = {name: [] for name in _ALLOWED_PARTITIONS}
        for row in rows:
            by_partition[row.partition].append(_parse_aware(row.as_of_utc))
        if by_partition["train"] and by_partition["validation"]:
            if max(by_partition["train"]) >= min(by_partition["validation"]):
                raise ValueError("fuga temporal: train se solapa con validation")
        if by_partition["validation"] and by_partition["test"]:
            if max(by_partition["validation"]) >= min(by_partition["test"]):
                raise ValueError("fuga temporal: validation se solapa con test")
        if by_partition["train"] and not by_partition["validation"] and by_partition["test"]:
            if max(by_partition["train"]) >= min(by_partition["test"]):
                raise ValueError("fuga temporal: train se solapa con test")


class FootballDatasetBuilder:
    def __init__(self, *, dataset_name: str, split_policy: TemporalSplitPolicy) -> None:
        if not isinstance(dataset_name, str) or not dataset_name.strip():
            raise ValueError("dataset_name no puede estar vacío")
        self.dataset_name = dataset_name.strip()
        self.split_policy = split_policy

    def assign_partitions(self, rows: Iterable[FootballResearchRow]) -> list[FootballResearchRow]:
        assigned: list[FootballResearchRow] = []
        fixture_partition: dict[str, str] = {}
        for row in sorted(rows, key=lambda item: (item.as_of_utc, item.fixture_id)):
            desired = self.split_policy.partition_for(row.as_of_utc)
            existing = fixture_partition.get(row.fixture_id)
            if existing is not None and existing != desired:
                # Keep the entire fixture in the earliest partition determined by its
                # first observation. This is safer than splitting snapshots of one game.
                desired = existing
            else:
                fixture_partition[row.fixture_id] = desired
            assigned.append(
                FootballResearchRow(
                    fixture_id=row.fixture_id,
                    as_of_utc=row.as_of_utc,
                    partition=desired,
                    features=dict(row.features),
                    labels=dict(row.labels),
                    label_observed_at_utc=row.label_observed_at_utc,
                    source_provider=row.source_provider,
                )
            )
        TemporalLeakageGuard.validate_rows(assigned)
        TemporalLeakageGuard.validate_partition_order(assigned)
        return assigned

    def write_version(
        self,
        rows: Iterable[FootballResearchRow],
        *,
        output_root: str | Path,
        dataset_version: str,
        created_at_utc: str | None = None,
        metadata: dict[str, int | float | str | bool | None] | None = None,
    ) -> FootballDatasetManifest:
        if not isinstance(dataset_version, str) or not dataset_version.strip():
            raise ValueError("dataset_version no puede estar vacío")
        assigned = self.assign_partitions(rows)
        created_at = created_at_utc or datetime.now(timezone.utc).isoformat()
        _parse_aware(created_at)

        version_dir = Path(output_root) / self.dataset_name / dataset_version
        if version_dir.exists() and any(version_dir.iterdir()):
            raise FileExistsError("una versión de dataset es inmutable y ya existe")
        version_dir.mkdir(parents=True, exist_ok=True)

        row_payload = [asdict(row) for row in assigned]
        data_bytes = b"\n".join(_canonical_json(item) for item in row_payload)
        if data_bytes:
            data_bytes += b"\n"
        data_path = version_dir / "rows.jsonl"
        data_path.write_bytes(data_bytes)

        feature_names = tuple(sorted({name for row in assigned for name in row.features}))
        label_names = tuple(sorted({name for row in assigned for name in row.labels}))
        counts = {name: sum(1 for row in assigned if row.partition == name) for name in sorted(_ALLOWED_PARTITIONS)}
        manifest = FootballDatasetManifest(
            dataset_name=self.dataset_name,
            dataset_version=dataset_version,
            created_at_utc=created_at,
            row_count=len(assigned),
            fixture_count=len({row.fixture_id for row in assigned}),
            partition_counts=counts,
            source_providers=tuple(sorted({row.source_provider for row in assigned})),
            feature_names=feature_names,
            label_names=label_names,
            data_sha256=sha256(data_bytes).hexdigest(),
            split_policy={
                "train_end_utc": self.split_policy.train_end_utc,
                "validation_end_utc": self.split_policy.validation_end_utc,
                "test_end_utc": self.split_policy.test_end_utc,
            },
            metadata={} if metadata is None else dict(metadata),
        )
        manifest_path = version_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(asdict(manifest), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest

    @staticmethod
    def load_version(version_dir: str | Path) -> tuple[FootballDatasetManifest, list[FootballResearchRow]]:
        root = Path(version_dir)
        raw_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest = FootballDatasetManifest(
            **{
                **raw_manifest,
                "source_providers": tuple(raw_manifest["source_providers"]),
                "feature_names": tuple(raw_manifest["feature_names"]),
                "label_names": tuple(raw_manifest["label_names"]),
                "metadata": dict(raw_manifest.get("metadata", {})),
            }
        )
        data = (root / "rows.jsonl").read_bytes()
        if sha256(data).hexdigest() != manifest.data_sha256:
            raise ValueError("checksum del dataset no coincide con el manifest")
        lines = [line for line in data.splitlines() if line.strip()]
        if len(lines) != manifest.row_count:
            raise ValueError("row_count del manifest no coincide con rows.jsonl")
        rows = [FootballResearchRow(**json.loads(line.decode("utf-8"))) for line in lines]
        TemporalLeakageGuard.validate_rows(rows)
        TemporalLeakageGuard.validate_partition_order(rows)
        if len({row.fixture_id for row in rows}) != manifest.fixture_count:
            raise ValueError("fixture_count del manifest no coincide con rows.jsonl")
        observed_features = tuple(sorted({name for row in rows for name in row.features}))
        observed_labels = tuple(sorted({name for row in rows for name in row.labels}))
        if observed_features != manifest.feature_names:
            raise ValueError("feature_names del manifest no coincide con rows.jsonl")
        if observed_labels != manifest.label_names:
            raise ValueError("label_names del manifest no coincide con rows.jsonl")
        return manifest, rows

    @staticmethod
    def verify_version(version_dir: str | Path) -> FootballDatasetManifest:
        manifest, _ = FootballDatasetBuilder.load_version(version_dir)
        return manifest
