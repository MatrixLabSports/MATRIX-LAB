# Provider Data Rights & Licensing Governance Policy V19

## Purpose

MATRIX must not treat technical access to sports data as permission to store, transform, train on, display, redistribute, commercialize, export, sublicense, or retain that data indefinitely.

## Mandatory provider-rights evidence

Every governed provider must have a versioned rights profile bound to reviewed evidence containing at least:

- provider identity;
- exact rights-profile fingerprint;
- source/contract reference;
- fingerprint of the reviewed terms or agreement;
- reviewer role;
- review/effective/expiry timestamps;
- review outcome;
- evidence strength;
- revocation status;
- independent review reference when contractual evidence is claimed.

Missing, future-dated, expired, revoked, rejected, mismatched, or unknown-strength evidence fails closed.

## Rights are granular

Rights are evaluated independently for:

- ingestion;
- caching;
- raw storage;
- historical retention;
- derivative creation;
- model training;
- internal analytics;
- internal display;
- customer display;
- public/customer redistribution;
- commercial use;
- backup;
- export;
- sublicensing.

A right in one category never implies another.

## Scope restrictions

Every use request is bound to the exact provider, purpose, sport, competition scope, territory, data form, retention request, attribution plan, and timestamp.

## Retention and attribution

Provider-specific raw/cache retention limits are enforced. Required attribution must be planned before the use is allowed.

## High-risk use

Customer-facing display, redistribution, commercial use, and sublicensing require stronger evidence. Public terms alone do not automatically prove commercial redistribution rights.

## Multi-provider derived data

Derived datasets and model artifacts must preserve rights lineage to every source provider. The combined use inherits the most restrictive source assessment; one permissive provider cannot expand another provider's rights.

## Versioning and terms changes

A changed terms fingerprint or rights profile may not be hidden behind the same profile version. Reuse of an evidence ID for materially changed content is blocked.

## Termination

The rights profile records the reviewed post-termination data treatment. Deletion obligations require verification; uncertain post-termination treatment remains under review rather than being assumed permissive.

## Non-goals

This software does not interpret contracts, replace legal counsel, or self-certify intellectual-property/database/licensing compliance. A software PASS means the registered evidence and internal controls are coherent enough for the next governed review.

Provider-rights governance may block or place a use in WATCH. It may not promote a model or enable automatic wagering.
