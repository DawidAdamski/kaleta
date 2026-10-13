---
plan_id: encryption-posture-research
title: Research — encryption posture beyond operator-blind (Posture 2 and true E2EE)
area: security
effort: large
status: draft
roadmap_ref: ../roadmap.md#strategic-direction-open-core
---

# Research: encryption posture beyond operator-blind

**This is a research/design track, not an implementation plan.** It exists so the
considerations the team raised while scoping [`horizontal-scaling`](horizontal-scaling.md)
are not lost. It is deliberately open-ended and a good candidate for a dedicated
agent/spike later. Nothing here ships without its own follow-up plan and ADR
changes.

## Why this exists
`horizontal-scaling` ships **Posture 1** (sticky sessions, keys stay in pod
memory, operator-blind preserved — no ADR change). Two bigger questions were
explicitly deferred and should be studied on their own:

1. **Posture 2** — seamless pod failover by letting any pod reconstruct the
   account DEK, at the cost of operator-blindness.
2. **True end-to-end encryption (E2EE)** — whether Kaleta could be rearchitected
   so that *even an active-session operator* cannot read account data.

Both bump into the same theorem from `horizontal-scaling`: **if the server can
compute over plaintext while a user is signed in (ADR-35 requires exactly this —
every total, budget, forecast is a SQL query), then the infrastructure holds the
plaintext at that moment, so a sufficiently privileged operator can too.**
E2EE and server-side aggregation are in fundamental tension. This track is about
how far we can push toward confidentiality *without* losing the product.

## Vocabulary (to avoid the KEK collision)
- **DEK** — the per-account data key (AES-256-GCM), ADR-35. Unlocked into pod
  memory from a member's passphrase; encrypts every user-written column.
- **member KEK** — ADR-35's key, stretched (Argon2id) from a member's *data
  passphrase*, wraps that member's private key. **Operator never holds it.**
- **operator unwrap key** — a *new*, cluster/operator-held key (ideally in a
  KMS) proposed only in Posture 2 to wrap the DEK for cross-pod sharing. Holding
  it is what breaks operator-blindness. **Not** the member KEK.

## Posture 2 — operator-unwrappable DEK cache (seamless failover)
**Sketch.** On unlock, the pod wraps the DEK with the operator unwrap key and
writes `wrapped_dek` to Valkey, namespaced per (tenant, member), with a TTL.
Any pod, on a `KeyRing` miss, fetches and unwraps it — no re-unlock. Plaintext
DEKs stay memory-only; Valkey holds only ciphertext.

**What it buys.** No re-unlock on failover/scale-in/rollout; true elastic
multi-pod; HPA-friendly.

**What it costs (the honest part).**
- The operator (KMS/unwrap-key holder) can decrypt any account **with a live
  session** — ADR-35's "operator cannot read" becomes "operator can read
  active-session data". That is the normal SaaS posture, but it is a real
  downgrade and must be disclosed.
- New high-value secret (the unwrap key) with its own rotation, access control
  and blast radius. A KMS (AWS KMS / GCP KMS / Vault Transit) is the right home;
  pod env is the weak form.
- Valkey becomes security-relevant: AUTH + TLS, no (or encrypted) persistence for
  the keyring namespace, short TTLs, network isolation.

**To study / decide.**
- Exactly which threat model we are offering (operator-honest-but-curious?
  compromised-Valkey-only? compromised-pod?). Map each to what leaks.
- TTL vs UX: how long a wrapped DEK may live; refresh-on-activity.
- Whether Posture 2 is a **paid-tier opt-in** while the free/self-hosted default
  stays operator-blind (Posture 1).
- ADR-35 amendment + `privacy.md` wording; this must not be silent.

## True E2EE — the harder question
The dream: the server never holds plaintext, so neither does the operator, ever.
For a **server-rendered app whose core value is server-computed analytics**
(ADR-35, NiceGUI), classic E2EE is not a drop-in. Options, roughly ordered by
how much they change the product:

1. **Client-side crypto + server stores ciphertext only.** The browser
   encrypts/decrypts; the server stores blobs. Kills every server-side
   aggregate (budgets, net worth, forecasts, reports) unless re-implemented in
   the browser over fully-downloaded data — i.e. a different app (SPA, not
   NiceGUI), with Prophet/analytics moved client-side. Largest rewrite; strongest
   confidentiality.
2. **Searchable / homomorphic / order-preserving encryption** so the server
   aggregates over ciphertext. Partially possible (sums via additively-homomorphic
   schemes, equality via deterministic encryption — which ADR-35 already uses for
   unique names), but general reporting (group-by, forecasting) is not practical
   with today's tooling, and each scheme leaks something. Research-heavy, likely
   partial.
3. **Confidential computing / TEEs (enclaves).** The server still computes on
   plaintext, but inside an attestable enclave the operator cannot introspect;
   keys only enter the enclave. Keeps the server-rendered analytics model while
   removing the operator from the trust boundary. Heavy ops/infra lift
   (SEV-SNP/TDX/Nitro Enclaves), attestation, and it is only as good as the TEE.
   The most promising "keep the product, remove the operator" path.
4. **Hybrid**: keep server-side analytics operator-blind via Posture-1-style
   per-session keys (operator can read only during an active session, as today's
   hosted plan already implies), and reserve full E2EE (option 1) for a distinct
   "vault" subset of fields the server never needs to compute on.

**To study / decide.**
- What confidentiality we actually promise vs market (self-hosted is already the
  strong-privacy answer — does hosted need E2EE, or is operator-blind-at-rest +
  Posture 1 enough?).
- Which fields truly need server computation vs could be client-only (option 4).
- A spike on TEEs (option 3) for the hosted tier — feasibility and cost.
- Cost/benefit vs the open-core roadmap: E2EE may be a premium differentiator or
  a distraction from shipping features.

## Explicitly not decided here
Everything. This document frames the questions and the trade space; each chosen
direction becomes its own plan with its own ADR (amending or superseding
ADR-35) before any code.
