# V8 Findings 002 and 003 - Remote Freshness Closure

Status: CLOSED pending commit/tag completion in this gate.

## Scope

This record closes the rollback/freshness findings only. It does not authorize
production PostgreSQL, real provider execution, automatic provider switching,
automatic model promotion, or automatic wagering.

## Evidence

- AWS RDS PostgreSQL used as an authority outside the local Windows host.
- TLS certificate-chain and server identity verification used with sslmode=verify-full.
- RDS force-SSL behavior verified.
- Governed V001 schema applied through a separate migrator role.
- Runtime role verified as least privilege and not owner of the authority table.
- PostgresFreshnessRoot lifecycle verified against the remote engine.
- Real row-lock concurrency produced exactly one prepare winner.
- Canonical lifecycle local snapshot rollback was rejected while remote root remained ahead.
- Provider lifecycle local snapshot rollback was rejected while remote root remained ahead.
- Remote root did not regress and no pending reservation was introduced by rejected rollback.
- PostgreSQL/freshness/security regression family passed.
- Complete MATRIX test suite passed in G4-F.

## Finding disposition

V8 Finding-002: CLOSED.
Reason: stale internally consistent local snapshots can no longer be accepted when
the independent remote freshness root is ahead.

V8 Finding-003: CLOSED.
Reason: the freshness authority is demonstrably outside the local rollback fault
domain and coordinated rollback of local SQLite/sidecars is detected fail-closed.

## Gates remaining closed

POSTGRES_PRODUCTION_AUTHORIZED=FALSE
REAL_PROVIDER_EXECUTION_AUTHORIZED=FALSE
AUTOMATIC_PROVIDER_SWITCH=FALSE
AUTOMATIC_MODEL_PROMOTION=FALSE
AUTOMATIC_WAGERING=FALSE

No merge is performed by this closure.