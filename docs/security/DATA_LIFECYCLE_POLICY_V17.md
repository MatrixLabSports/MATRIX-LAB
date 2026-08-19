# DATA LIFECYCLE POLICY — V17

The governed technical lifecycle is:

`INGESTED → VALIDATED → ACTIVE → ARCHIVED → DELETION_PENDING → DELETED`

`QUARANTINED` is a controlled exception state reachable from non-deleted stages. `DELETED` is terminal.

Rules:

1. Every lifecycle event is timezone-aware and linked to the previous event fingerprint.
2. Asset identity and asset fingerprint are immutable across the chain.
3. Time cannot move backwards.
4. Legal hold blocks deletion-pending and deleted states and cannot be removed by a lifecycle transition.
5. A `DELETED` transition requires completed deletion evidence for the same asset and the same source fingerprint.
6. Deletion evidence must already be complete before the lifecycle event records deletion.
7. A broken or manually altered lifecycle chain fails closed.

Legal-hold release must be governed by a separate authorization process; V17 deliberately does not implement an implicit release path.
