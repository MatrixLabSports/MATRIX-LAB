# MATRIX Football - Private Live C2

## Scope

`PRIVATE_INTERNAL_ONLY` is the platform scope for this installation.

In scope:
- private/internal football analytics;
- internal modeling and dashboard use;
- point-in-time live observations;
- descriptive live pressure features;
- live odds movement and velocity;
- append-only-style durable evidence with integrity verification.

Out of scope:
- customer/public display;
- data resale or redistribution;
- sublicensing;
- commercial service delivery;
- automatic wagering.

## Provider boundary

C2 does not create a raw HTTP client, socket, transport, API key, or
provider authorization. The one-shot live capture function requires an
already-governed client supplied by the existing MATRIX provider stack.

Every new API-Football response is passed through the existing
`validate_api_football_response_envelope` boundary before use.

The first real provider call remains a separate human-controlled,
bounded probe because the current preflight found no API-Football
credential in the process environment. That probe must not receive a
secret through chat or source control.

## Point-in-time discipline

The bundle records a UTC capture timestamp after the provider responses
are obtained. Missing provider statistics remain `None`; they are never
silently converted to zero. Pressure features are descriptive deltas and
shares only. No betting thresholds are invented by this block.

## Live odds

Movement is defined from two observations of the same provider,
bookmaker, fixture, market, and selection.

- lower decimal odds -> `STEAM`;
- higher decimal odds -> `DRIFT`;
- equal odds -> `UNCHANGED`.

The module records percentage change, change velocity per minute and
implied-probability delta. Cross-book agreement is descriptive evidence,
not an automatic entry rule.

## Decision timing

The timing model supports:

- `DESCARTAR`;
- `VIGILAR`;
- `PRESENAL`;
- `ENTRADA`;
- `VENTANA_CERRADA`.

It records data freshness, decision latency, signal confirmation timing
and optional missed-entry reasons. It does not execute a wager.

## Next controlled gate

After installation and independent regression verification:

`C2_BOUNDED_REAL_PROVIDER_LIVE_PROBE`

That gate requires secure local credential provisioning plus an explicit
human authorization for the bounded network probe.
