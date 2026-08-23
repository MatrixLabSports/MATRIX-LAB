# Football bounded LIVE executor — R8.1R1 semantic manifest hardening

## Why R8.1R1 exists

The independent R8.1 I6 audit reproduced three blocking bypasses in the durable
planned-run manifest:

- the manifest did not independently re-derive the finite provider-call plan;
- the manifest did not independently re-derive the modality allowlist;
- the manifest did not independently re-derive the football fixture subject
  contract.

Those symptoms share one architecture root: a manifest could be constructed
directly without re-running the executor configuration contract.

## Hardening

R8.1R1 re-derives a complete `BoundedFootballLiveExecutorConfig` from every
durable manifest before it can be accepted. The re-derived config must match:

- provider key;
- football fixture subject key;
- modality allowlist and uniqueness;
- capture-round limit;
- total provider-call limit;
- runtime limit;
- one attempt per slot;
- no calibrated capture interval yet;
- odds disabled;
- single-process only;
- cross-process execution forbidden;
- no automatic retry;
- no automatic provider switch;
- no automatic model promotion;
- no automatic wagering;
- production inadmissible.

`planned_provider_calls` must equal the re-derived finite plan cardinality and
the stored `config_fingerprint` must equal the fingerprint of that independently
re-derived configuration.

The SQLite manifest store also performs a strict semantic round trip:
parsed durable JSON must equal `manifest.payload()` after re-derivation. This
prevents re-hashed changes to ignored control fields, extra fields, stop
conditions, or state-machine metadata from being treated as valid evidence.

## Scope unchanged

R8.1R1 remains offline foundation work only. It has no provider execution,
network access, repeated polling, executor loop, persistent sequence allocator,
or production admission. Cross-process determinism remains unproven.

The next gate is an independent R8.1R1 re-audit. R8.2 remains blocked until
that audit reports zero blocking findings.
