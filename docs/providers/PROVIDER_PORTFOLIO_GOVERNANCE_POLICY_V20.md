# MATRIX-LAB-SPORTS — Provider Portfolio Governance Policy V20

## Purpose
V20 governs whether an already-authorized data provider is operationally suitable for a defined role. Provider legal/data rights remain governed separately by V19. Operational fitness never overrides missing rights.

## Core rules
1. A provider cannot be promoted solely because it has the best aggregate score or lowest price.
2. Hard gates are evaluated first: rights, freshness of evidence, availability, latency, data freshness, coverage, quality, identifier stability, error rate, quota reserve, expected quota demand, cost policy, and provider incidents.
3. Percentages are represented as integer basis points and money as integer cents in governed fingerprints. Floating point values are prohibited in release fingerprints.
4. Missing, stale, future-dated, mismatched or internally inconsistent operational evidence fails closed.
5. PRIMARY, SECONDARY and REFERENCE roles are explicit and non-interchangeable.
6. Every governed portfolio requires at least one healthy SECONDARY provider.
7. A fallback is not considered resilient if it belongs to the same declared independence group as the PRIMARY provider.
8. Rights must pass independently for every provider, including reference and fallback sources.
9. Quota planning must preserve a reserve and prove enough capacity for the next governed window.
10. Projected cost must stay inside the approved budget policy; cost may never compensate for quality, rights, latency or resiliency failures.
11. Failover readiness requires a recent drill with bounded recovery time, zero data-loss events, compatible schema, reconciled identifiers, successful reconciliation and revalidated provider rights.
12. Duplicate events during a failover drill cause WATCH and require investigation; data loss causes BLOCK.
13. Portfolio plans require human approval. V20 may compute readiness but may not self-certify provider suitability.
14. V20 does not enable automatic wagering, model promotion or live-money execution.
15. The V20 gate does not itself switch providers. Later runtime automation may only use a portfolio after independent production-readiness controls approve the automated failover mechanism.

## Status semantics
- `PASS`: all hard controls pass and failover evidence is current.
- `WATCH`: no hard control failed, but one or more warning conditions require attention.
- `BLOCK`: one or more hard controls failed; the provider/portfolio is not operationally eligible for the governed role.

## Separation of concerns
- V19 answers: **Are we allowed to use this provider/data for this purpose?**
- V20 answers: **Is this provider operationally fit, sustainable and resilient for this role right now?**
- Neither V19 nor V20 answers: **Should a wager be placed?**
