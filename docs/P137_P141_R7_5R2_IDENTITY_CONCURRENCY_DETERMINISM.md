# P137-P141 R7.5R2 — Reservation-aware canonical identity writer determinism

## Purpose

R7.5R2 is the corrected execution package for the independently reproduced
same-process canonical identity concurrency window.

R7.5R1 proved the reservation-aware transaction map and the writer-lock
placement, then stopped at the pre-commit quality gate because its source
rewriter indented blank lines inside the wrapped transaction block. That
created trailing whitespace only; no commit was created.

The R7.5R1 rollback reached the exact R7.4R1 HEAD, but its cleanup routine used
an error-producing Git probe for the new untracked documentation file. On
PowerShell that probe surfaced as a RemoteException after the hard reset.
R7.5R2 therefore includes a bounded recovery step for that one known untracked
R7.5R1 document and uses non-throwing tracked-file checks during rollback.

## Current freshness protocol

The canonical lifecycle append path is reservation-aware:

1. verify external checkpoint;
2. verify current freshness authority;
3. perform transactional domain validation;
4. append lifecycle and tail-guard evidence;
5. prepare the freshness transition;
6. COMMIT SQLite;
7. finalize the freshness transition;
8. synchronize the external tail checkpoint;
9. resolve failed freshness transitions when necessary.

R7.5R2 does not depend on the obsolete post-COMMIT
`synchronize_freshness_root` hook.

## Concurrency hardening

A path-scoped in-process re-entrant writer lock is shared by all
`SQLiteCanonicalIdentityLifecycleLedger` instances resolving to the same
canonical database path. The lock is acquired after the existing pre-
transaction read/validation phase and covers the current reservation protocol
from `BEGIN IMMEDIATE` through failure resolution.

The source rewriter preserves blank lines as truly blank lines, so wrapping the
transaction does not introduce trailing whitespace.

## Safety boundaries

- Scope: same Python process and same resolved canonical SQLite path.
- Cross-process deterministic serialization is not claimed.
- No network or provider execution is authorized.
- Repeated polling and bounded repeatable execution remain unauthorized.
- No automatic provider switching, model promotion, or wagering is enabled.
- Production remains inadmissible.
- Independent R7.5R2 audit is mandatory before reconsidering the executor
  design gate.
