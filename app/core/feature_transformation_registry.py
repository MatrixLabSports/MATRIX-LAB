from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


def _canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class TransformationInput:
    schema_name: str
    schema_version: str
    fields: tuple[str, ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "fields": list(self.fields),
        }


@dataclass(frozen=True)
class FeatureTransformation:
    transformation_id: str
    sport: str
    entity_type: str
    transformation_key: str
    transformation_version: str
    artifact_sha256: str
    output_feature_definition_fingerprints: tuple[str, ...]
    inputs: tuple[TransformationInput, ...]
    transformation_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.feature-transformation/1",
            "transformation_id": self.transformation_id,
            "sport": self.sport,
            "entity_type": self.entity_type,
            "transformation_key": self.transformation_key,
            "transformation_version": self.transformation_version,
            "artifact_sha256": self.artifact_sha256,
            "output_feature_definition_fingerprints": list(
                self.output_feature_definition_fingerprints
            ),
            "inputs": [item.payload() for item in self.inputs],
            "transformation_fingerprint": self.transformation_fingerprint,
            "automatic_model_promotion": False,
            "automatic_transformation_promotion": False,
        }


@dataclass(frozen=True)
class FeatureTransformationIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


class SQLiteFeatureTransformationRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_transformations (
                    transformation_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    transformation_key TEXT NOT NULL,
                    transformation_version TEXT NOT NULL,
                    transformation_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    UNIQUE (
                        sport,
                        entity_type,
                        transformation_key,
                        transformation_version
                    ),
                    CHECK (sport IN ('football', 'tennis'))
                )
                """
            )

    @staticmethod
    def build_transformation(
        *,
        sport: str,
        entity_type: str,
        transformation_key: str,
        transformation_version: str,
        artifact_sha256: str,
        output_feature_definition_fingerprints: Sequence[str],
        inputs: Sequence[TransformationInput],
    ) -> FeatureTransformation:
        if sport not in {"football", "tennis"}:
            raise ValueError("INVALID_SPORT")

        for name, value in {
            "entity_type": entity_type,
            "transformation_key": transformation_key,
            "transformation_version": transformation_version,
        }.items():
            if not isinstance(value, str) or not value:
                raise ValueError(f"INVALID_{name.upper()}")

        artifact_sha256 = _hex64("ARTIFACT_SHA256", artifact_sha256)

        outputs = tuple(
            sorted(
                {
                    _hex64("OUTPUT_FEATURE_FINGERPRINT", value)
                    for value in output_feature_definition_fingerprints
                }
            )
        )
        if not outputs:
            raise ValueError("EMPTY_TRANSFORMATION_OUTPUTS")

        if (
            isinstance(inputs, (str, bytes))
            or not isinstance(inputs, Sequence)
            or not inputs
        ):
            raise ValueError("EMPTY_TRANSFORMATION_INPUTS")

        normalized_inputs: list[TransformationInput] = []

        for item in inputs:
            if not isinstance(item, TransformationInput):
                raise ValueError("INVALID_TRANSFORMATION_INPUT")
            if not item.schema_name or not item.schema_version or not item.fields:
                raise ValueError("INVALID_TRANSFORMATION_INPUT")

            fields = tuple(sorted(set(item.fields)))
            if len(fields) != len(item.fields):
                raise ValueError("DUPLICATE_TRANSFORMATION_INPUT_FIELD")

            normalized_inputs.append(
                TransformationInput(
                    schema_name=item.schema_name,
                    schema_version=item.schema_version,
                    fields=fields,
                )
            )

        normalized_inputs = sorted(
            normalized_inputs,
            key=lambda item: (
                item.schema_name,
                item.schema_version,
                item.fields,
            ),
        )

        base = {
            "schema": "matrix.feature-transformation/1",
            "sport": sport,
            "entity_type": entity_type,
            "transformation_key": transformation_key,
            "transformation_version": transformation_version,
            "artifact_sha256": artifact_sha256,
            "output_feature_definition_fingerprints": list(outputs),
            "inputs": [item.payload() for item in normalized_inputs],
            "automatic_model_promotion": False,
            "automatic_transformation_promotion": False,
        }

        transformation_fingerprint = _sha(base)
        transformation_id = _sha(
            {
                "schema": "matrix.feature-transformation-id/1",
                "transformation_fingerprint": transformation_fingerprint,
            }
        )

        return FeatureTransformation(
            transformation_id=transformation_id,
            sport=sport,
            entity_type=entity_type,
            transformation_key=transformation_key,
            transformation_version=transformation_version,
            artifact_sha256=artifact_sha256,
            output_feature_definition_fingerprints=outputs,
            inputs=tuple(normalized_inputs),
            transformation_fingerprint=transformation_fingerprint,
        )

    @classmethod
    def _verify_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> FeatureTransformation:
        inputs = tuple(
            TransformationInput(
                schema_name=item["schema_name"],
                schema_version=item["schema_version"],
                fields=tuple(item["fields"]),
            )
            for item in payload["inputs"]
        )

        expected = cls.build_transformation(
            sport=payload["sport"],
            entity_type=payload["entity_type"],
            transformation_key=payload["transformation_key"],
            transformation_version=payload["transformation_version"],
            artifact_sha256=payload["artifact_sha256"],
            output_feature_definition_fingerprints=payload[
                "output_feature_definition_fingerprints"
            ],
            inputs=inputs,
        )

        if expected.payload() != payload:
            raise ValueError("TRANSFORMATION_SEMANTIC_INTEGRITY_VIOLATION")

        return expected

    def register(
        self,
        transformation: FeatureTransformation,
    ) -> FeatureTransformation:
        expected = self.build_transformation(
            sport=transformation.sport,
            entity_type=transformation.entity_type,
            transformation_key=transformation.transformation_key,
            transformation_version=transformation.transformation_version,
            artifact_sha256=transformation.artifact_sha256,
            output_feature_definition_fingerprints=(
                transformation.output_feature_definition_fingerprints
            ),
            inputs=transformation.inputs,
        )

        if expected != transformation:
            raise ValueError("TRANSFORMATION_DERIVATION_MISMATCH")

        payload_json = _canonical_json(transformation.payload())
        payload_sha = sha256(payload_json.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT
                    transformation_id,
                    transformation_fingerprint,
                    payload_sha256
                FROM feature_transformations
                WHERE
                    sport = ?
                    AND entity_type = ?
                    AND transformation_key = ?
                    AND transformation_version = ?
                """,
                (
                    transformation.sport,
                    transformation.entity_type,
                    transformation.transformation_key,
                    transformation.transformation_version,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute("ROLLBACK")
                if (
                    str(existing[0]) == transformation.transformation_id
                    and str(existing[1])
                    == transformation.transformation_fingerprint
                    and str(existing[2]) == payload_sha
                ):
                    return transformation
                raise ValueError("TRANSFORMATION_VERSION_MUTATION_VIOLATION")

            connection.execute(
                """
                INSERT INTO feature_transformations (
                    transformation_id,
                    sport,
                    entity_type,
                    transformation_key,
                    transformation_version,
                    transformation_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transformation.transformation_id,
                    transformation.sport,
                    transformation.entity_type,
                    transformation.transformation_key,
                    transformation.transformation_version,
                    transformation.transformation_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute("COMMIT")

        return transformation

    def get_by_fingerprint(
        self,
        fingerprint: str,
    ) -> Mapping[str, Any] | None:
        fingerprint = _hex64("TRANSFORMATION_FINGERPRINT", fingerprint)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    transformation_id,
                    transformation_fingerprint,
                    payload_json,
                    payload_sha256
                FROM feature_transformations
                WHERE transformation_fingerprint = ?
                """,
                (fingerprint,),
            ).fetchone()

        if row is None:
            return None

        transformation_id, stored_fp, payload_json, stored_sha = row
        payload = json.loads(payload_json)
        actual_sha = sha256(
            _canonical_json(payload).encode("utf-8")
        ).hexdigest()

        if actual_sha != stored_sha:
            raise ValueError("TRANSFORMATION_PAYLOAD_HASH_MISMATCH")

        expected = self._verify_payload(payload)
        if (
            expected.transformation_id != transformation_id
            or expected.transformation_fingerprint != stored_fp
        ):
            raise ValueError("TRANSFORMATION_REDERIVATION_MISMATCH")

        return payload

    def audit_integrity(self) -> FeatureTransformationIntegrityReport:
        errors: list[str] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT transformation_fingerprint
                FROM feature_transformations
                ORDER BY transformation_id
                """
            ).fetchall()

        for (fingerprint,) in rows:
            try:
                self.get_by_fingerprint(fingerprint)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                errors.append(f"{error}:{fingerprint}")

        return FeatureTransformationIntegrityReport(
            ok=not errors,
            records=len(rows),
            errors=tuple(errors),
        )
