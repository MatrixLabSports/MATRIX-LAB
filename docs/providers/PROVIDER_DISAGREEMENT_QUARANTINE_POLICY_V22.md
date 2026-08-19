# Provider Disagreement, Quarantine & Source-of-Truth Policy V22

1. Cross-provider disagreement is never resolved by provider priority alone.
2. Canonical fixture identity disagreements and required-market identity disagreements are non-tiebreakable and must be quarantined.
3. Score and event-state disagreements require an independent third source or explicit human review; a source-of-truth rule may not automatically override them.
4. Statistics and timing may use a governed source-of-truth rule only when the rule is active, scoped to the exact sport/competition/domain, supported by SHA-256 evidence, human-approved, independently reviewed, and above the configured confidence threshold.
5. An independent third source must be a distinct provider and, when required by policy, belong to a distinct independence group from both disagreeing sources.
6. A third source may downgrade a dispute from quarantine to WATCH when it clearly supports one side. It does not authorize an automatic provider switch.
7. If the third source supports neither side, the evidence remains quarantined.
8. Quarantine expiration never means automatic release. Expired records require new review evidence.
9. Quarantine release requires an exact quarantine fingerprint, a resolution fingerprint, human approval, independent review, successful required checks, and temporally valid evidence.
10. V22 may block, quarantine, or mark evidence WATCH. It may not promote models, switch providers automatically, certify universal source-of-truth status, or enable wagering.
