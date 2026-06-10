# ADR 0016 — Credential-gap escalation in the gated onboarding workflow

**Status:** Accepted

**Date:** 2026-06-10

## Context

ADR 0011 ratifies the gated onboarding graph, ADR 0013 closes
prose-field handling, and ADR 0014 introduces the first "structural
gap" escalation pattern (enum-gap) for cases where the agent cannot
proceed because macrodb's vocabulary cannot represent the candidate
series' methodology faithfully.

All four prior ADRs (0011 through 0014) silently assume the agent can
reach providers when it tries. In practice the agent cannot: many
providers require an API key, an auth header, or other credential
material before research can do meaningful probe fetches. Without
those, `research` cannot do its job — probes fail with 401/403, the
drafter has nothing to ground its proposal in, and the operator's
investment in the session is wasted.

The operator's framing throughout the design space has been
unambiguous: **the agent must never force**. Two failure modes apply
to credentials specifically:

- **Coerce / barrel through.** The agent ignores authentication, fails
  every probe, produces a hollow proposal, and leaves the operator to
  guess at what went wrong.
- **Abort hard.** Session ends. The operator restarts later with
  credentials in place. Discards research and intake context.

The right third path is the same shape as enum-gap: pause, surface a
structured request to the operator, let them provision the credential
out of band, and resume the session with the credential available. The
fact that the operator needs the credential pre-Gate-1 (research and
`validate_script` both make real provider calls) creates a wrinkle
that enum-gap does not have.

`providers.credentials_ref` exists in CONTEXT.md as the intended
column holding a reference to the secret material; the actual key
value never enters macrodb. The provider's auth scheme, rate limits,
and tier metadata also need to be durable so the ingestion runtime can
respect them at execution time.

ADR 0014 established the structural pattern for "agent-proposes,
operator-acts, session-pauses, resume-verifies" escalations. The
question for this ADR is whether credential-gap is the same node and
state surface as enum-gap, a separate but symmetric pattern, or a
brand-new shape.

## Decision

Add credential-gap as a **sibling escalation pattern** to enum-gap.
Mirror enum-gap's shape and audit lifecycle, but with a distinct
graph node, distinct state fields, distinct audit values, and a
distinct verification mechanism.

### The graph: distinct nodes, shared helpers

A new node `credential_gap_wait` joins the graph as a peer of
`enum_gap_wait`. Both are pure-interrupt picker nodes with no LLM
call. They share implementation under `agent/escalation/` (picker
rendering, pause checkpointing, clean CLI exit, audit-row emission)
but expose distinct state and audit surfaces.

Distinct nodes (rather than one generic `escalation_wait`) preserve:

- **Per-kind audit queryability.** "Show me every credential I
  provisioned for the agent" is a single SQL filter on
  `target_type = CREDENTIAL_REF`. A generic node would force
  discriminator filtering inside `proposed_data` JSONB.
- **Per-kind verification mechanics.** Enum-gap verifies via Python
  introspection plus DB CHECK constraint check. Credential-gap
  verifies via HTTP probe. Forcing both behind one node interface
  produces a switch statement, not a coherent abstraction.
- **Per-kind evolution.** Each gap's anti-patterns, evidence schema,
  and discipline can drift independently without affecting the other.
- **ADR 0014 continuity.** No retroactive amendment to a
  just-accepted ADR.

The shared shape lives in **the workflow doc as the "Escalation gaps"
pattern** and in shared Python helpers, not in a polymorphic node
type.

### Scope: keys plus the access metadata the runtime needs

The credential-gap proposal carries the env var name plus the
**access metadata** the ingestion runtime needs to use the credential
correctly: auth scheme (Bearer header vs query param vs custom header
vs basic auth), rate limit config (requests per minute / hour / day,
tier label, notes), and the provider's ref URL for the auth docs.

OAuth flows, IP allowlists, custom client certificates, and other
non-key access mechanisms are **out of scope** for v1. The
`AuthScheme` enum is closed (see below); if a future provider needs
an auth scheme not in the enum, that triggers an enum-gap escalation
on `AuthScheme`, which then unblocks the credential-gap. The two
escalation patterns compose cleanly.

The agent never records the credential value. The schema has no field
for it. The audit row's `proposed_data` JSONB never contains it. The
only thing that ever touches the value is the in-memory probe code
that reads `os.environ.get(<env_var_name>)` and passes it through to
the HTTP client.

### Detection: at `research`, with a three-layer pre-check

Detection lives in the `research` role. Before emitting a
credential-gap proposal, research performs a **three-layer pre-check**,
in order, cached per `(provider_identity, env_var_name)` pair per
session:

1. **If the provider already exists in `providers` with a non-null
   `credentials_ref`,** read that column and use its env var name as
   the probe target (instead of inferring a fresh `<PROVIDER>_API_KEY`
   convention). The operator may have provisioned this credential in
   a previous session; the provider row remembers the name.
2. **Check `os.environ.get(<env_var_name>)`.** If empty or unset,
   pre-check fails; gap proceeds.
3. **Run a real probe with the credential present.** If 200 OK with
   sensible payload, pre-check passes; no gap is emitted; the session
   continues using the env var. If 401/403 against an env var name
   inferred fresh for a provider with no blessed `credentials_ref`,
   pre-check fails and the gap proceeds (first-time missing/invalid
   credential). If 401/403 against an env var that came from an
   existing `credentials_ref` (layer 1), the credential was
   previously blessed and has rotated or lost quota — surface that as
   a research-phase error (operator admin work), not a gap. If a
   transient (5xx, network), retry per the v1 retry policy; on retry
   exhaustion, surface as a research-phase error, not a gap. The probe
   is the ground truth.

This makes "redundant ask" structurally impossible: the gap can only
fire when the credential is actually missing or invalid.

### Provider-row write timing: deferred to Gate 1

Credential-gap fires from `research`, *before* Gate 1. The gate model
in ADR 0011 says no catalog writes happen before Gate 1 approves.
This ADR honours that invariant.

**Credential-gap-apply does NOT touch `providers`.** It records the
operator's provisioning event in `change_proposals` (env var name,
auth scheme, rate limits, evidence) and verifies the probe works. The
agent reads the env var directly from `os.environ` during research
and `validate_script`. At Gate 1 `apply_catalog`, the `providers` row
is INSERTED (new provider) or UPDATED (existing provider) with
`credentials_ref`, `auth_scheme`, `rate_limit_config` populated from
the audit row.

If the session aborts after credential-gap-apply but before Gate 1,
the operator's env var setup is preserved (it's on their machine) and
the audit row records what they did, but the catalog has no
half-finished provider row. Future sessions can re-use the env var,
and the first session that reaches Gate 1 against that provider
populates the provider row with the access metadata then.

This is **asymmetric with enum-gap**, which commits enum-widening
immediately (because the operator's action is a code commit + Alembic
migration — real persistent infrastructure regardless of the
session). Credential-gap doesn't write a `providers` row at apply
time because there's no catalog reality to attach to until Gate 1
crowns the provider as real.

### Human interrupt: new node `credential_gap_wait`

`credential_gap_wait` is a human-interrupt node distinct from
`gate_1_wait` and `enum_gap_wait`. It renders, for each gap:

- the provider identity (existing UUID or proposed name + URLs)
- the proposed env var name
- the proposed auth scheme
- the inferred rate limit (operator can confirm or edit)
- the cited evidence URL and snippet establishing key requirement
- the rationale
- inline operator instructions: how to set the env var, where to
  obtain a key (provider's auth docs link), and the exact resume
  command

It then offers a **2-option structured picker**:

- **Apply later (pause)** — session checkpoints; CLI exits cleanly.
  Operator obtains the key out of band, sets the env var in their
  shell or secret store, and resumes with
  `macrodb onboard --resume <session-id>`. Audit row is created with
  `validation_status = pending_human_apply`.
- **Abort** — operator types a rationale (required); session
  terminates via the existing `abort` node with reason
  `credential_unavailable`. Audit row is created with
  `validation_status = declined_by_operator`.

There is intentionally **no third "Decline and override" option**
(asymmetric with enum-gap's "Decline and coerce"). The override case
("I believe no key is needed despite the docs") is rare and the
probe is the ground truth — the cheapest path is for the operator to
"Apply later" with `<env_var_name>` left unset; the resume probe runs
without a key and either succeeds (proving the operator right) or
fails (proving the agent right). The picker doesn't have to be the
place that decision is made.

If a real "this provider is public" disagreement surfaces in
practice, it travels through chat-level Request changes — operator
types "I think this provider is public; re-research without
assuming a key", research re-runs with an `assume_no_credential`
hint, and the probe decides. No audit signal is needed because the
session re-investigates with new context rather than committing to
a curatorial decision.

### Pause / resume verification

Two state fields drive the lifecycle:

- `credential_gap_proposals: list[CredentialGapProposal]` (set by
  `research` when pre-check fails)
- `credential_gap_resolutions: list[CredentialGapResolution]` (set in
  `credential_gap_wait` after probe verification on resume)

`CredentialGapProposal` carries `provider_identity`,
`proposed_env_var_name`, `proposed_auth_scheme`, `inferred_rate_limit`,
`evidence_url`, `evidence_snippet`, and `rationale`.

`ProviderIdentity` is a discriminator that handles three cases:

- `kind == "new"` — brand-new provider; carries
  `proposed_provider_name`, `proposed_provider_homepage_url`,
  `proposed_provider_doc_url`. `apply_catalog` will INSERT.
- `kind == "existing"` — provider row exists; carries
  `existing_provider_id`. `apply_catalog` will UPDATE.

`CredentialGapResolution` carries `outcome ∈ {provisioned,
provisioned_renamed, aborted}`, `applied_env_var_name`,
`applied_auth_scheme`, `applied_rate_limit_config`,
`operator_rationale` (required when `outcome == aborted`), and
`resolved_at`. There is no `declined` outcome: the 2-option picker has
no `Decline and coerce` branch (that is enum-gap's `declined_coerce`),
so the only negative terminal is `aborted`.

On resume, `credential_gap_wait` walks each pending proposal and
re-runs the probe with the env var. Cases:

1. **Env var set and probe succeeds.** Record
   `outcome = provisioned`, populate `applied_*` fields from the
   confirmed config.
2. **Env var unset and operator pasted a different env var name in
   chat at resume time** (the renamed case). The wait node prompts:
   "Probe with `<proposed_env_var_name>` failed (env var not set).
   Did you use a different env var name? If so, type it in chat."
   On the operator's reply with a new name, re-probe. On success,
   record `outcome = provisioned_renamed` and
   `applied_env_var_name = <the new name>`.
3. **Env var set but probe fails 401/403.** The credential is wrong.
   Re-render the picker with a "Probe failed: 401/403" message so the
   operator can rotate or abort.
4. **Env var set but probe fails transient (5xx, network).** Retry
   per the v1 retry policy. On exhaustion, surface as a research
   error.

All gaps must be resolved (`provisioned`, `provisioned_renamed`, or
`aborted`) before research can complete and the graph can advance.
Partial resolution across multiple resumes is fine.

### No parallel reviewer scrutiny

Unlike enum-gap, credential-gap proposals do **not** flow through the
parallel reviewer fan-out. The reviewer node is reached only after
`draft_proposal`, which is downstream of `research`. Credential-gap
pauses *before* `draft_proposal`, so there is no Gate-1-time review
opportunity.

The discipline (three conditions, per-proposal evidence, anti-pattern
list) is enforced **at the drafter** (the `research` role emitting
the gap) via the `skill-credential-gap` skill body, plus the
**drop-on-missing-evidence** rule that demotes evidenceless gaps to
"attempt without a key, record the result, continue research." The
operator sees the evidence at the wait node and is the final arbiter.

This is weaker defense in depth than enum-gap. It is appropriate for
v1 because the decision being made is simpler ("do I have access to
this provider"), the cost of a false-positive gap is one operator
interruption (not a wrong catalog row), and the operator is the
person both running the session and provisioning the credential —
they have the relevant context to spot a bad ask immediately.

If credential-gap false-positives become a problem in practice, a
lightweight pre-wait governance check can be added as a follow-on
without changing this ADR.

### Audit trail in `change_proposals`

Each credential-gap proposal produces **its own** `change_proposals`
row, created at the point the operator picks `Apply later (pause)` or
`Abort`. The row is linked to the session via `source_agent_session_id`
but its lifecycle is independent of the session's main onboarding
proposal.

Schema deltas on the governance enums:

- `Action`: new value `suggest_credential_provisioning`
- `TargetType`: new value `CREDENTIAL_REF`

Existing values reused:

- `ValidationStatus.pending_human_apply` (ADR 0013) — applies between
  pause and resume
- `ValidationStatus.applied_by_operator` (ADR 0013) — set on
  successful probe verification at resume
- `ValidationStatus.declined_by_operator` (ADR 0014) — set on Abort

| Operator action | `change_proposals.status` | Item `validation_status` |
|---|---|---|
| Picks Apply later; resume probe succeeds | `applied` | `applied_by_operator` |
| Picks Apply later; resume probe succeeds with renamed env var | `applied` | `applied_by_operator`; `proposed_data` records the rename |
| Picks Abort | `rejected` | `declined_by_operator`; `proposed_data` records `operator_rationale` |
| Session aborts mid-session for unrelated reasons | `rejected` | `declined_by_operator` |

The audit row records *what the operator did*, not whether the
session succeeded. If the operator provisions a credential and then
the session aborts at Gate 1 for unrelated reasons, the audit row
stays `applied` because the credential reference is real and
re-usable in a future session.

### Schema additions

On `providers`:

- `auth_scheme: AuthScheme | None` — column-backed enum CHECK
  constraint per ADR 0005.
- `rate_limit_config: dict | None` — JSONB column. Shape:
  `{requests_per_minute, requests_per_hour, requests_per_day,
  tier_label, notes}`, all fields nullable. The ingestion runtime
  reads the tightest defined constraint and respects it.
- `credentials_ref: str | None` — already specified in CONTEXT.md;
  add to the model if not present.

New enum:

- `AuthScheme` in
  [src/macro_foundry/enums/provider.py](../../src/macro_foundry/enums/provider.py),
  values: `BEARER_HEADER`, `QUERY_PARAM`, `HEADER_CUSTOM`,
  `BASIC_AUTH`, `NONE`. OAuth and other flows explicitly deferred.
  Adding new values follows the enum-gap escalation pattern from
  ADR 0014 if the agent ever encounters a provider whose auth
  scheme is none of these.

All schema deltas land as one Alembic migration alongside the
governance-enum widenings.

### Coordination with the ingestion runtime

The ingestion runtime reads `providers.auth_scheme` to construct
HTTP requests with the right auth applied; it reads
`providers.rate_limit_config` to schedule polling respecting the
tightest defined cap. Both reads happen via the existing
`IngestionFeed → SeriesSource → Provider` relationship; no new
foreign keys are needed.

The runtime uses `os.environ.get(<providers.credentials_ref>)` to
retrieve the credential value at execution time, exactly as the
agent's research probes do during onboarding. If the env var is
unset at runtime, the feed execution fails with a recorded error
in `ingestion_run_logs.error_message`. There is no separate
"refresh credentials" workflow in v1; if the env var becomes
unset, the operator restores it and the next scheduled run
succeeds.

## Consequences

**Positive.**

- "Agent never forces" becomes a structural guarantee for credentials
  the same way it is for vocabulary. Coercion (barrelling through
  without a key) is not on the drafter's path; the only progress
  options are operator-action or operator-abort.
- The agent can do real probes and comprehensive investigation during
  research because the credential is available pre-Gate-1.
- The audit trail in `change_proposals` is queryable: "show me every
  credential I provisioned for the agent" is one SQL filter.
- Security: the credential value never enters macrodb. The schema
  has no field for it.
- The ingestion runtime gains durable rate-limit metadata, so
  scheduled polling can respect provider caps without re-asking the
  operator.
- Composition with enum-gap works cleanly: a provider with an
  unusual auth scheme triggers an enum-gap on `AuthScheme` first,
  then the credential-gap once the new value exists.
- Pre-check makes "redundant ask" structurally impossible. If the
  operator already has the credential provisioned from a previous
  session, the agent finds it and proceeds without interruption.

**Negative.**

- One more interrupt node (`credential_gap_wait`), one more skill
  (`skill-credential-gap`), one new `Action` value
  (`suggest_credential_provisioning`), one new `TargetType` value
  (`CREDENTIAL_REF`), one new column-backed enum (`AuthScheme`), two
  new columns on `providers` (`auth_scheme`, `rate_limit_config`),
  and likely one new column (`credentials_ref`) if it does not yet
  exist in the model.
- Asymmetries with enum-gap (provider-row write deferred to Gate 1;
  no parallel reviewer scrutiny; 2-option picker instead of 3) have
  to be documented carefully; they are correct here but they are
  exceptions to the otherwise-symmetric pattern. Workflow doc
  carries the documentation; the asymmetries are spelled out
  explicitly.
- No defense in depth for false-positive credential gaps. The
  discipline lives at the drafter and the operator is the only
  reviewer. v1 accepts this; if false-positives become a problem,
  a lightweight pre-wait check can be added later.
- `AuthScheme` is a closed enum in v1; OAuth providers cannot be
  onboarded until OAuth flow design lands. Acceptable scoping for
  v1; recorded as a deferred follow-up.

**Impact on PRD #32 and issue slicing.** The follow-on PRD must add
slices for: `agent/escalation/` shared helpers (also serving
ADR 0014), `credential_gap_wait` node, `skill-credential-gap`,
`AuthScheme` enum, schema additions to `providers`, and the
`research`-node pre-check. The first credential-gap-capable session
will be the smoke that proves the path end-to-end.

## Alternatives considered

- **One generic `escalation_wait` node handling enum-gap and
  credential-gap (and any future gap kind).** Rejected. The
  verification mechanics are disjoint (Python introspection vs
  HTTP probe). The audit fields are disjoint (enum_path vs env var
  name + auth scheme + rate limits). The "shared abstraction" is
  fictional — what's actually shared is rendering and pause/resume
  plumbing, which can live in helpers without forcing a polymorphic
  node. Distinct nodes preserve per-kind audit queryability and
  per-kind evolution. ADR 0014 stays intact.
- **Single ADR covering both enum-gap and credential-gap as
  "structural gap escalation."** Rejected. ADR 0014 was just
  accepted and is internally coherent on its own terms. Folding
  credential-gap into it retroactively would erode immutability.
  A sibling ADR that cites ADR 0014 as the established pattern is
  the right shape.
- **3-option picker mirroring enum-gap's
  Apply / Decline-and-coerce / Abort.** Rejected. The override case
  ("treat as no-key") is rare, risky, and the probe gives the
  truth anyway. Chat-level Request changes handles the rare case
  without giving it structural prominence on the picker.
- **Provider-row write at credential-gap-apply time.** Rejected.
  Punctures the gate invariant that nothing is committed before
  Gate 1. The asymmetry with enum-gap (which does commit at apply
  time) is principled because enum-gap's operator action is real
  persistent infrastructure (code + migration), while
  credential-gap's operator action is operator-machine state that
  needs a catalog identity to attach to before it becomes a
  durable schema fact.
- **Audit-row-only metadata; no schema additions to `providers`.**
  Rejected. The ingestion runtime needs to read rate limits at
  execution time. Audit rows are operational records, not the right
  durable source for runtime-read fields.
- **Separate `provider_access_config` table, 1:1 with `providers`.**
  Rejected. Provider identity and provider access policy do not
  drift independently; they belong on the same row. 1:1 tables are
  a smell that almost always refactors back to columns.
- **Free-chat exchange between research and operator instead of a
  structured picker.** Rejected. Pause/resume safety and audit
  trail both require structured fields. The chat layer can carry
  context and free-text rationale alongside the picker, but the
  high-stakes signal must be a deliberate operator action with a
  typed outcome.
- **OAuth support in v1's `AuthScheme` enum.** Rejected as scope.
  OAuth flows carry token-refresh lifecycles, redirect URIs, and
  client secrets that have their own design surface. Deferred to a
  future ADR if and when an OAuth-only provider becomes
  load-bearing for onboarding.
- **Including endpoint-level rate limits in `rate_limit_config`.**
  Rejected for v1. Provider-level limits cover the common case.
  Endpoint-level handling can be added later via a schema delta on
  `ingestion_feeds` or `series_sources` if a real provider needs it.
