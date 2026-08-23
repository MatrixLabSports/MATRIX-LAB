# Football bounded LIVE executor — R8.1R2 durable manifest authority hardening

## Why this repair exists

Independent audit I7 confirmed that R8.1R1 closed all three I6 semantic
re-derivation defects, but found four additional blockers in the durable
planned-run authority record:

- `crash_recovery_required` could be set to false;
- `idempotent_resume_required` could be set to false;
- the design and independent-audit SHA authorities were caller supplied;
- `run_id` could not be re-derived because the run nonce was not durable.

These were correctly classified as blockers before R8.2.

## R8.1R2 contract

R8.1R2 makes recovery requirements fail closed: both crash recovery and
idempotent resume must remain true in every valid manifest.

The R8.1 release authority is pinned to the exact approved evidence:

- R8 design manifest SHA-256:
  `02cd645bf0eccdac6ea27151ae63bbaf350a197adecc1d443359a19bb83c97fa`
- independent I5R1 audit SHA-256:
  `8bcad0d5064b2a52fc9580a139f285a7b2f4b9a7acc14bd078501024d94b34b6`

The normal manifest builder no longer accepts governance SHA values from its
caller. Direct construction remains possible for parsing/testability, but
`__post_init__` rejects any authority value not equal to those release-pinned
hashes.

`run_nonce_sha256` is now durable manifest evidence. `run_id` is independently
re-derived from the durable config fingerprint, UTC creation time, durable run
nonce, approved design SHA, and approved audit SHA. Any mismatch fails closed.

The existing strict durable JSON semantic round-trip remains required.

## Scope unchanged

This is still an offline foundation. It does not implement the sequence
allocator, recovery execution protocol, executor loop, provider calls,
repeated polling, production admission, provider switching, model promotion,
or wagering. Cross-process determinism remains unproven.

R8.2 stays blocked until an independent R8.1R2 audit reports zero blockers.
