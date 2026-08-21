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
