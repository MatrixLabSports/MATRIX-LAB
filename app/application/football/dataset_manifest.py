from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.core.dataset_manifest import (
    DatasetRowEvidence,
    build_dataset_manifest,
    verify_dataset_manifest,
)


def build_football_dataset_manifest(
    *,
    dataset_key: str,
    as_of: str,
    rows: Sequence[DatasetRowEvidence],
):
    return build_dataset_manifest(
        sport="football",
        dataset_key=dataset_key,
        as_of=as_of,
        rows=rows,
        policy_version="P51-FOOTBALL/1",
    )


def verify_football_dataset_manifest(
    *,
    manifest: Mapping[str, Any],
    rows: Sequence[DatasetRowEvidence],
):
    if manifest.get("sport") != "football":
        return False, ("SPORT_BOUNDARY_VIOLATION",)

    return verify_dataset_manifest(
        manifest=manifest,
        rows=rows,
    )
