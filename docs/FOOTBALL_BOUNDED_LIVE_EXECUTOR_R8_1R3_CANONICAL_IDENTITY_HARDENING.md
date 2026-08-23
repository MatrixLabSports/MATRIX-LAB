# Football bounded LIVE executor — R8.1R3 canonical identity hardening

## Why this repair exists

Corrected independent audit I8R1 found two blockers before R8.2:

- the football fixture subject key accepted non-canonical identities such as
  empty, non-numeric, signed, zero, decimal/fraction, internal-whitespace, and
  leading-zero fixture IDs;
- direct manifest construction could retain outer-whitespace aliases in
  `provider_key` or `subject_key` in memory even though the re-derived config
  normalized them.

Durable persistence already failed closed on those aliases through manifest
fingerprint re-derivation. R8.1R3 closes the remaining identity ambiguity
before a persistent sequence allocator is introduced.

## Canonical subject contract

After trimming outer whitespace, the football subject key must be exactly:

`fixture:<positive base-10 decimal integer>`

The identifier must begin with `1-9` and all remaining characters must be
ASCII `0-9`. Therefore zero, signs, leading zero aliases, internal whitespace,
non-digits, decimals, and fractions are rejected.

Examples accepted:

- `fixture:1`
- `fixture:1557375`
- outer whitespace around the entire key is normalized before validation.

## Manifest canonicalization

Every durable run manifest still re-derives the complete executor config.
R8.1R3 now writes the canonical `provider_key` and `subject_key` from that
re-derived config back into the frozen manifest during validation.

A direct manifest built with harmless outer-whitespace aliases therefore
becomes byte-for-byte semantically equivalent to the canonical manifest:
same canonical fields, config fingerprint, run ID, manifest fingerprint, and
durable payload. Persisting the alias followed by the canonical form is an
exact idempotent replay, not an identity collision.

## Scope unchanged

No provider call, executor loop, repeated polling, sequence allocator,
production admission, automatic provider switch, model promotion, or wagering
is authorized. Cross-process determinism remains unproven.

R8.2 remains blocked until an independent R8.1R3 audit reports zero blockers.
