BEGIN;

CREATE SCHEMA matrix_security;

CREATE TABLE matrix_security.matrix_freshness_root_schema (
    schema_version INTEGER PRIMARY KEY,
    contract_id TEXT NOT NULL,

    CONSTRAINT matrix_freshness_root_schema_version_v1
        CHECK (schema_version = 1),

    CONSTRAINT matrix_freshness_root_contract_v1
        CHECK (
            contract_id = 'matrix.postgres-freshness-root/1'
        )
);

INSERT INTO matrix_security.matrix_freshness_root_schema (
    schema_version,
    contract_id
)
VALUES (
    1,
    'matrix.postgres-freshness-root/1'
);

CREATE TABLE matrix_security.matrix_freshness_root (
    namespace TEXT PRIMARY KEY,

    current_sequence_id BIGINT NOT NULL,
    current_commitment_sha256 TEXT,

    pending_transaction_id TEXT,
    pending_expected_sequence_id BIGINT,
    pending_expected_commitment_sha256 TEXT,
    pending_intended_sequence_id BIGINT,
    pending_intended_commitment_sha256 TEXT,

    CONSTRAINT matrix_freshness_root_namespace_nonempty
        CHECK (
            btrim(namespace) <> ''
        ),

    CONSTRAINT matrix_freshness_root_current_sequence_nonnegative
        CHECK (
            current_sequence_id >= 0
        ),

    CONSTRAINT matrix_freshness_root_current_state_valid
        CHECK (
            (
                current_sequence_id = 0
                AND current_commitment_sha256 IS NULL
            )
            OR
            (
                current_sequence_id > 0
                AND current_commitment_sha256
                    ~ '^[0-9a-f]{64}$'
            )
        ),

    CONSTRAINT matrix_freshness_root_pending_state_valid
        CHECK (
            (
                pending_transaction_id IS NULL
                AND pending_expected_sequence_id IS NULL
                AND pending_expected_commitment_sha256 IS NULL
                AND pending_intended_sequence_id IS NULL
                AND pending_intended_commitment_sha256 IS NULL
            )
            OR
            (
                pending_transaction_id IS NOT NULL
                AND btrim(pending_transaction_id) <> ''

                AND pending_expected_sequence_id IS NOT NULL
                AND pending_intended_sequence_id IS NOT NULL

                AND pending_expected_sequence_id >= 0

                AND (
                    (
                        pending_expected_sequence_id = 0
                        AND pending_expected_commitment_sha256 IS NULL
                    )
                    OR
                    (
                        pending_expected_sequence_id > 0
                        AND pending_expected_commitment_sha256
                            ~ '^[0-9a-f]{64}$'
                    )
                )

                AND (
                    (
                        pending_intended_sequence_id = 0
                        AND pending_intended_commitment_sha256 IS NULL
                    )
                    OR
                    (
                        pending_intended_sequence_id > 0
                        AND pending_intended_commitment_sha256
                            ~ '^[0-9a-f]{64}$'
                    )
                )

                AND pending_expected_sequence_id =
                    current_sequence_id

                AND pending_expected_commitment_sha256
                    IS NOT DISTINCT FROM
                    current_commitment_sha256

                AND pending_intended_sequence_id >=
                    pending_expected_sequence_id

                AND (
                    pending_intended_sequence_id >
                        pending_expected_sequence_id
                    OR
                    (
                        pending_intended_sequence_id =
                            pending_expected_sequence_id

                        AND pending_intended_commitment_sha256
                            IS NOT DISTINCT FROM
                            pending_expected_commitment_sha256
                    )
                )
            )
        )
);

COMMIT;
