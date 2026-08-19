# MATRIX V19 — Provider Data Rights & Licensing Governance

V19 adds a provider-neutral evidence layer so technical data access is never confused with legal/contractual permission to use data.

Core controls:

- versioned provider rights profiles;
- exact terms/evidence SHA-256 binding;
- scope by provider, sport, competition, purpose and territory;
- independent rights for ingestion, caching, storage, history, derivatives, model training, display, redistribution, commercial use, backup, export and sublicensing;
- retention and attribution enforcement;
- high-risk commercial/customer-facing evidence escalation;
- multi-provider lineage where the weakest source rights govern the composite;
- immutable/versioned terms-change detection;
- contract expiry/revocation monitoring;
- post-termination data-disposition controls;
- a fail-closed provider-rights integration gate.

## Non-goals

V19 does not determine what a provider contract legally means and does not declare licensing, copyright, database-right, or commercial-use compliance. Those conclusions require external competent review and current provider evidence.

`automatic_model_promotion_enabled=False` and `automatic_wager_execution_enabled=False` remain invariant.
