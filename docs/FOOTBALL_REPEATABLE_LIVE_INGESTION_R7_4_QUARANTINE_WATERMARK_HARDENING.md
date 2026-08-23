# Football Repeatable LIVE Ingestion R7.4

R7.4 closes the independent I2 findings that remained after R7.3.

## Closed blocking findings

1. A quarantined late observation no longer advances the accepted sequence watermark.
2. A quarantined out-of-order observation no longer advances the accepted observed-at watermark.

Durable quarantined rows remain in the ledger and remain covered by membership/integrity controls. They are excluded only from future admission watermarks.

## Provider-aware table identity

The legacy table-level uniqueness contract is migrated from a provider-blind key to a provider-aware key. The stream-level unique index remains provider-aware and global across correlation IDs.

Migration from ledger user version 73 to 74 is transactional and fail-closed. Existing rows must validate under R7.4 semantics; incompatible history is not silently rewritten.

## Stream state

`football_live_stream_state` schema advances to `/2`.

- `record_count` counts all durable rows, including quarantined evidence.
- `membership_sha256` covers all durable observation fingerprints.
- `max_sequence_id` is the maximum accepted sequence only.
- `max_observed_at` is the maximum accepted observation time only.

This preserves audit evidence without allowing rejected evidence to poison future accepted-stream watermarks.

## Governance

R7.4 does not add provider execution, network calls, repeated polling, production thresholds, model promotion, provider switching, or wagering. Production remains inadmissible.

The prior canonical-CI concurrency failure from I2 was not reproduced by D1 (20/20 exact-test PASS, module PASS, canonical CI PASS). R7.4 therefore does not modify the unrelated identity subsystem; canonical CI remains a mandatory pre/post-commit gate.
