# Provider Normalization, Reconciliation & Failover Consistency Policy V21

1. Provider-specific identifiers are never treated as canonical identifiers. Every governed entity mapping must be explicit, versioned, time-bounded when necessary, and linked to SHA-256 evidence.
2. Missing or conflicting active crosswalks fail closed. Low-confidence or unreviewed mappings produce WATCH rather than silent acceptance.
3. Fixture identity is canonicalized by sport, fixture ID, competition, participants, kickoff and optional venue/round context. Home/away reversal is a blocking mismatch.
4. Provider snapshots must use timezone-aware timestamps and exact integer values. Release fingerprints continue to forbid floats.
5. Cross-provider reconciliation compares the same canonical fixture at comparable observation/event times. Excessive observation skew or stale/future evidence fails closed.
6. Critical state disagreements (fixture, participants, terminal state, score) block failover readiness.
7. Required statistics must exist in both providers. Small configured integer deltas may be WATCH; deltas above policy block.
8. Market reconciliation protects exact market identity: market type, period, selection and exact line. `OVER 2.5` and `OVER 3.5` are different markets.
9. Provider prices are not required to be equal. Price disagreement can be legitimate market information and belongs to odds/CLV evidence, not identity reconciliation.
10. A single successful reconciliation is insufficient for failover readiness. V21 requires a recent, gap-bounded window of consecutive reconciliations for the exact primary/fallback pair.
11. Any BLOCK inside the consistency window blocks readiness. WATCH samples require explicit policy and never silently become PASS.
12. V21 does not enable automatic provider switching, automatic model promotion, wagering, or production certification.
13. PASS means normalization/reconciliation evidence is technically coherent for governed review; it is not a contractual, legal, provider or production certification.
