# P137–P141 — Historical Data & Identity Lifecycle Governance

Status at implementation start: `main=0618068`.

## Scope

This block extends the existing historical and point-in-time foundations without replacing them.

Existing components remain authoritative for their original purposes:

- `SQLiteCanonicalIdentityRegistry`: immutable canonical identity registration.
- `SQLiteProviderIdentityMappingLedger`: provider-to-canonical observations available as-of knowledge time.
- `SQLiteCanonicalObservationStore`: durable admitted observations, append-only and point-in-time queryable.
- `build_point_in_time_history`: historical reconstruction without future leakage.
- football fixture repository: current-state `upsert/reconcile` semantics.
- provider temporal truth: provider fact correction/supersession, not canonical identity lifecycle.

## P137 — Canonical identity lifecycle

Canonical IDs remain immutable. Alias, display-name change and canonical supersession are stored as separate append-only lifecycle evidence.

Aliases are evidence only and MUST NOT become a name-based join or resolution mechanism.

Display-name changes and supersession require explicit lifecycle events. They do not mutate the original canonical registry row.

Supersession is bitemporal: `effective_at` represents when the identity fact applies; `known_at` represents when MATRIX knew it. Queries before `known_at` must not see future knowledge.

## P138 — Temporal provider identity lifecycle

Stable provider entity IDs are mapped through append-only temporal binding evidence with explicit:

- `valid_from`
- `valid_to`
- `known_at`
- correction lineage
- predecessor lineage

A provider-ID reassignment is represented by an atomic remap: append a correction that closes the previous interval, then append the successor interval. Historical queries before the remap became known retain the previously known mapping.

No name-based provider mapping is permitted.

## P139 — Historical preservation

Identity lifecycle never rewrites stored historical observations or canonical IDs. Historical data remains append-only and is interpreted through point-in-time lifecycle views.

The football fixture repository remains a current-state repository and is not reclassified as an append-only history store.

## P140 — Sport separation

Football and tennis expose separate application adapters. Cross-sport canonical bindings fail closed.

Core lifecycle primitives may be shared only where the semantics are sport-neutral.

## P141 — Governance and safety

Permanent invariants:

- `name_join_allowed = FALSE`
- `automatic_model_promotion = FALSE`
- `automatic_provider_switch = FALSE`
- `automatic_wagering = FALSE`
- Missing values remain distinct from zero.
- No future knowledge may enter point-in-time history.
- No destructive SQL update/delete is allowed in the new lifecycle ledgers.
- Identity remap and canonical supersession require human review.
- Existing canonical/history stores are not silently migrated or rewritten.

Promotion beyond this block requires focused tests, canonical CI, full-suite non-regression, an internal 0/0/0 closure audit, and an independent adversarial re-audit before merge.


## V1 adversarial hardening: provider mapping knowledge causality

Independent adversarial re-audit V1 identified that a successor provider identity binding could reference a predecessor whose `known_at` was later than the successor's own `known_at`.

This is forbidden because lineage cannot depend on knowledge that did not yet exist.

Rule:

- `successor.known_at < predecessor.known_at` => reject.
- `successor.known_at == predecessor.known_at` => allowed for an atomic remap transaction.
- `successor.known_at > predecessor.known_at` => allowed when the successor is learned later.

Canonical CI must preserve this invariant.


## V2 adversarial hardening: linked predecessor boundary freeze

Independent adversarial re-audit V2 demonstrated that correcting an already-linked predecessor after a successor existed could move the predecessor's `valid_to`.

That could create either:

- overlap with the successor interval, causing ambiguous point-in-time identity resolution; or
- a gap before the successor interval, leaving historical event time without an identity mapping.

Governed rule:

- A binding may be corrected/closed before a successor is linked.
- Once any binding references it through `predecessor_binding_id`, that predecessor is frozen.
- Later direct correction of that linked predecessor is rejected.
- Any future need to revise an already-linked historical chain requires a separately governed chain-resegmentation design; it must not be simulated by mutating one interval locally.

This preserves continuous, non-overlapping temporal identity lineage.


## V3 adversarial hardening: stale predecessor and supersession graph

Independent adversarial re-audit V3 found two related lineage risks.

First, a corrected provider identity binding could still be referenced later through its obsolete `binding_id` as a predecessor. This could recreate overlap or gap even though the corrected head itself was protected.

Governed rule:

- If any later row has `corrects_binding_id == predecessor.binding_id`, that predecessor is stale.
- A stale predecessor is never eligible for a successor.
- Successors must reference the current corrected head.

Second, canonical supersession cycle detection must not depend only on the candidate event's `effective_at`. A retroactive edge can look acyclic at its own event time while completing a cycle that becomes active at a later event time.

Governed rule:

- The canonical supersession graph known as of the candidate's `known_at` must remain globally acyclic.
- Effective-time filtering is still used for point-in-time resolution, but it is not sufficient for graph-integrity admission.


## V4 adversarial hardening: globally acyclic persisted supersession ledger

Independent adversarial re-audit V4 exposed an ingestion-order edge case.

A supersession edge with later `known_at` could already be persisted. A reciprocal edge arriving later as backfill with an earlier `known_at` was evaluated only against facts whose `known_at` was less than or equal to the candidate. That preserved point-in-time semantics locally but allowed the persisted ledger as a whole to become cyclic.

Governed distinction:

- `known_at` continues to control what MATRIX may see in a point-in-time historical reconstruction.
- Admission integrity is stricter: the entire persisted canonical supersession graph plus the candidate must remain acyclic, regardless of ingestion order or the relative `known_at` values of already persisted edges.
- Out-of-order backfill remains allowed when the resulting global graph is acyclic.
- Acyclicity admission and point-in-time visibility are separate concerns and must not be conflated.

This prevents a future-known edge already present in durable storage from combining with an earlier-known backfilled edge to create an eventual cycle.


## V5 adversarial hardening: append-only tail truncation evidence

Independent adversarial re-audit V5 proved that per-row hashes cannot by themselves detect deletion of the final valid row. Both lifecycle ledgers now use a shared append-only tail guard. Every durable row receives an immutable hash-chained commitment. The guard uses `INTEGER PRIMARY KEY AUTOINCREMENT`, and `sqlite_sequence` acts as a durable sequence high-water mark.

`audit_integrity()` cross-checks record count, IDs, payload hashes, commitment hashes, chain continuity, sequence continuity, and the sequence high-water mark. Deleting the final lifecycle row is detected because its commitment remains. Deleting both the final lifecycle row and the final guard commitment is also detected because SQLite does not move the AUTOINCREMENT high-water backward on row deletion. Exact replay remains idempotent.

For databases that predate this control, an empty pristine guard is bootstrapped once from current durable row order. After that migration baseline, the guard is fail-closed rather than silently repaired. Production lifecycle and tail-guard modules remain append-only and provide no application `UPDATE` or `DELETE` path.

## V6 adversarial hardening: anti-rebaseline state and provider→terminal-canonical composition

Independent adversarial re-audit V6 exposed two different integrity boundaries.

### Tail-guard loss must not create a new baseline

The V5 commitment chain detected lifecycle-row truncation while the guard survived. V6 then removed the guard table itself and reopened the database. Rebuilding a guard from the remaining rows would incorrectly certify a truncated prefix as a fresh baseline.

The tail guard now has a separate durable initialization-state marker. Once a ledger has been initialized, loss of the commitment table is treated as evidence loss rather than as permission to bootstrap again. The ledger may reopen for audit, but integrity is false and new appends fail closed with `APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN` until a governed recovery procedure is performed.

A one-time compatibility path remains for databases that genuinely predate the initialization-state marker: an existing V5 commitment chain may be adopted only after it exactly matches the protected durable records. This is migration, not silent repair.

This protection is intentionally scoped to accidental or partial database tampering. A writer capable of destroying every local evidence structure can defeat any purely local SQLite proof; stronger adversarial guarantees require an external immutable anchor and belong to later SRE/security certification.

### Provider identity is raw history; terminal canonical identity is a composed view

A provider mapping may legitimately preserve the canonical ID that was historically assigned even if that canonical entity is later superseded. Rewriting the raw provider ledger would destroy provenance. Therefore the correct control is explicit bitemporal composition, not silent mutation.

Football and tennis now expose sport-specific `resolve_*_provider_terminal_canonical_as_of` functions. They first resolve the provider binding point-in-time and then resolve that binding's canonical ID through the canonical identity lifecycle at the same `as_of` and `event_time`. Consumers that need the current/terminal canonical identity must use this composed path rather than interpreting the raw provider binding ID as terminal.

Sport separation remains strict and no name-based join is introduced.

## V7R hardening: external anchor and transaction-scoped canonical revalidation

Corrected independent adversarial re-audit V7R exposed two separate integrity boundaries.

The commitment table and its initialization-state table lived in the same SQLite database. Destroying both could make a truncated prefix look like a never-initialized ledger. File-backed lifecycle ledgers now maintain a small external initialization anchor beside the SQLite database. A valid V6 database with intact state is migrated once by creating this anchor. A fresh empty database initializes normally. If prior initialization is proven by the external anchor while internal guard/state evidence disappears, bootstrap fails closed with `APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN`. A non-empty ledger whose guard and state were both absent before schema creation is also refused rather than silently adopted.

SQLite serialized physical writes, but canonical lifecycle validation occurred before `BEGIN IMMEDIATE`. Canonical append now performs a second mutable-state validation after acquiring the write transaction and on the same connection. It rechecks predecessor linearity, knowledge-time monotonicity, terminal status, duplicate aliases, display-name no-op protection, and the complete supersession graph. This closes same-identity forks and concurrent cross-identity supersession cycles.

Point-in-time read semantics and provider raw-history provenance remain unchanged. No automatic provider execution, provider switching, model promotion, or wagering is enabled.
