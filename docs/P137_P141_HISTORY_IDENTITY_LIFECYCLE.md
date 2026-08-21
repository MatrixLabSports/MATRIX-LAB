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
