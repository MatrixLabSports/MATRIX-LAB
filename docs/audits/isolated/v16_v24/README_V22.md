# MATRIX V22 — Provider Disagreement Resolution

V22 adds governed cross-provider disagreement handling, explicit quarantine, independent third-source tie-breaking, and field-scoped source-of-truth evidence.

It is deliberately fail-closed. Critical identity/market mismatches are quarantined. Score/state mismatches require independent evidence. Any successful tiebreak remains WATCH rather than silently becoming PASS.

Automatic provider switching, model promotion, and wagering remain disabled.
