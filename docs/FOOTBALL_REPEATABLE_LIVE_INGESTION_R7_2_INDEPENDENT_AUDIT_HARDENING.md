# Football Repeatable LIVE Ingestion — R7.2 Independent-Audit Hardening

Status: **offline foundation only**.

R7.2 closes five gaps found by an independent adversarial review after R7.1R2:

1. idempotent replay must revalidate persisted status/reason codes before returning;
2. cross-modal alignment requires at least two distinct modalities;
3. repeatable admission must be bound to durable accepted sequence evidence;
4. provider identity is explicit and must match across fused modalities;
5. source-record fingerprint is mandatory for repeatable football ingestion.

Temporal observation schema is upgraded to `matrix.live-temporal-observation/2`
to bind `provider_key` into the observation fingerprint.

Fail-closed compatibility rule:
legacy v1 temporal observations without provider identity are not silently
promoted into the v2 repeatable LIVE path. They require explicit migration or
remain inadmissible.

Still forbidden:
- repeated provider execution;
- repeated polling;
- production SLO claims;
- automatic provider switching;
- automatic model promotion;
- automatic wagering;
- retroactive LIVE promotion.

Next gate: independent audit of R7.2 before any bounded repeated-ingestion
executor is designed.
