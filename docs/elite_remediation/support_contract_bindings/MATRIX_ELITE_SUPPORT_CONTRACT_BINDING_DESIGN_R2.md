# MATRIX ELITE — Support-Contract Binding Variants R2

Status: **structural hardening candidate only**. This layer does not declare provider, sport, market, live, failover, or production support.

## Purpose

R2 preserves the immutable R49 historical layer and corrects the semantic weakness discovered by the independent post-R49 review: a path+SHA binding to a reusable primitive is not enough unless the binding also states the exact scope where that primitive is semantically applicable, is backed by direct tests, and fails closed outside that scope.

R2 therefore adds context-resolved, content-addressed support-contract binding variants. A binding resolves only when exactly one variant matches a complete `ScopeContext`. Zero matches, multiple matches, incomplete market identity, cross-sport market-family mismatch, missing live provider identity, unordered/equal failover providers, and environments outside `STAGING` or `SHADOW` fail closed.

## Canonical identity hardening

Predictive and LIVE scope contexts require explicit sport, market family, market variant, period, subject scope, line semantics, explicit line unit (including the literal `NONE` for non-line markets), and metric key. LIVE additionally requires provider identity. FAILOVER requires an ordered and distinct primary/secondary provider pair and a non-production environment.

The executable market contract validates all twelve preregistration candidate families across football and tennis, rejects cross-sport family identity, and binds a specific market variant, period, subject, selection schema, line semantics/unit, metric key, participant identity kind, provider-definition requirement and voidability class. A canonical SHA256 fingerprint covers the complete definition.

Settlement semantics are not assumed bookmaker-agnostic. `SettlementRuleDefinition` binds exact market version, venue, jurisdiction, validity interval, exact rule-source SHA256, outcome source, push policy, DNP policy, abandonment policy and postponement policy. Provider-specific rules remain real evidence; this structural layer cannot manufacture or self-certify them.

Failover rollback/failback is likewise explicit. In addition to rights, schema compatibility, identity reconciliation, human approval and drill evidence, a return to primary requires completed recovery backfill, primary watermark catch-up, zero unreconciled gaps, zero data-loss events and zero open incidents. Automatic provider switching is forbidden.

## Binding architecture

The registry contains exactly 21 required controls and preserves exactly 19 version-bearing identity fields. Every version-bearing binding exposes its exact `version_field`; `baseline_definition` and `risk_policy` remain required controls without an identity version field, matching the governing R4 contract.

Each `SupportContractBindingVariant` has a deterministic `MATRIX-SCB-R2/<control>/<variant>` version and a canonical SHA256 fingerprint over its applicability, exact implementation/test evidence references, blockers and non-promotion state. The registry statically rejects overlapping applicability for the same control before runtime resolution is allowed.

The substantive rebindings include: composite sport-agnostic structural OOS evaluation; composite odds/history binding; direct V15 dual-control tests for human approval; decision-replay evidence instead of bounded-live-control coincidence; provider temporal-truth evidence for event time; live-validation evidence for staleness; football-only LIVE applicability; `api_football`-specific shadow applicability; football-only failover identity reconciliation; and composite secondary-provider rights/portfolio evidence.

Three structural contracts were missing or materially insufficient and are implemented add-only in R2: canonical executable market semantics, exact settlement-rule binding, and provider failover rollback/failback barriers.

## Evidence and non-promotion boundary

R2 evidence references are exact path + SHA256 + semantic symbol/test anchors. Generic anchors such as bare `test_` are forbidden. R49 remains immutable historical evidence and is not rewritten or reinterpreted as support PASS.

All R2 variants remain `support_status=NOT_EVALUATED` and `support_declared=false`. Actual provider legal rights, provider-specific settlement sources, real admitted PIT data, real per-sport/per-market evaluation evidence, real timestamped market history, real shadow runs and real failover drills remain external evidence blockers.

No Supportability Pack, Candidate Inventory, Selection R2, Builder R2, Registry R3, Freeze R3, CONTROLLED_LIVE or production authorization is produced by this layer.

## Premutation validation

The corrected isolated Base regression passed 37 tests. After R2 hardening, the combined exact Base + R51 overlay regression passed 87 tests. These premutation runs validate target semantics and compatibility only; they do not replace the repository precommit auditor or the full canonical repository regression that must run on the user's exact repository before commit.

Canonical registry fingerprint at this target revision:

`db8a39dbda4a705c569a9566a06203ecba381bb4445ec5f8b7634794cd80cc80`

Next gate: freeze exact target bytes, run the independent target-byte auditor, then permit one governed add-only repository installation only if branch, HEAD, cleanliness, R49 immutability, all evidence refs and all tests remain exact.
