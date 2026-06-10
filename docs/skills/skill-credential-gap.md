# skill-credential-gap

**Status:** draft

The body is content-complete; the skill is held at `draft` until the
runtime exists to load it and the operator confirms the rendered
operator-instruction block at `credential_gap_wait` matches the
project's preferred env-var / secret-store conventions. Promote to
`accepted` after that review.

## Scope

How the `research` role recognises and reports a credential gap — a
candidate provider that cannot be reached because authentication
material is missing or invalid — and the discipline for when a
`CredentialGapProposal` may be emitted versus when the agent should
attempt without a key or abort with a recorded error.

This skill governs credential availability for HTTP-key-style
authentication only. It does not cover OAuth flows, IP allowlists, or
client-certificate authentication; those are deferred to future ADRs.
It does not cover transient probe failures (5xx, network errors,
rate-limit 429s); those are not credential issues and are handled by
the v1 retry policy.

The architectural rationale for this skill, the
`credential_gap_proposals` state field, the `credential_gap_wait`
node, the `suggest_credential_provisioning` action, the deferred
provider-row write timing, and the audit-row design lives in
[ADR 0016](../adr/0016-credential-gap-escalation.md). The shared
escalation pattern that credential-gap and enum-gap both follow is
documented in `docs/series_onboarding_workflow.md` under "Escalation
gaps".

## When triggered

- node is `research` and the pre-check has failed for a candidate
  provider, OR
- node is `validate_script` and the selector run produces a
  credential failure (rare; usually caught by `research`'s
  pre-check first). In this case the gap is emitted by
  `validate_script` and the graph routes back to
  `credential_gap_wait`.

The pre-check (three layers in order) is the gating mechanism:

1. If the provider already exists in `providers` with a non-null
   `credentials_ref`, read that column and use its env var name as
   the probe target. The operator may have provisioned this
   credential in a previous session; do not ask again.
2. Check `os.environ.get(<env_var_name>)`. If empty or unset,
   pre-check fails; gap proceeds.
3. Run a real probe with the credential present. 200 OK with sensible
   payload → pre-check passes; no gap. 401 or 403 → pre-check fails;
   gap proceeds. Transient (5xx, network) → retry per the v1 retry
   policy; on exhaustion, surface as a research error, not a gap.

Pre-check results are **cached per `(provider_identity, env_var_name)`
pair per session**, so a research phase that probes twelve endpoints
of the same provider does not pay twelve pre-check probes.

## Body

### The three conditions (all required)

A gap may be emitted only when all three of these hold. The drafter
must articulate each one before the proposal is allowed to leave the
`research` role.

1. **The provider materially requires a key for the data being
   onboarded.** Provider documentation explicitly states that
   authentication is required for the endpoints or datasets in
   scope. "The provider has an API key registration page" is not
   sufficient — many providers offer optional keys that increase
   rate limits but allow keyless access. The standard is "the data
   we want cannot be reached without authentication."
2. **The pre-check confirmed the credential is missing or invalid.**
   A gap may not be emitted while `providers.credentials_ref` points
   at an env var whose probe returns 200. This makes "redundant ask"
   structurally impossible.
3. **Direct evidence from provider documentation supports the
   requirement.** A cited URL plus a quoted snippet from the
   provider's authentication or access documentation. Inferred
   evidence ("vendor providers usually need a key") is not
   sufficient.

### Per-proposal evidence structure

Every `CredentialGapProposal` must carry, at minimum:

- `provider_identity` — `ProviderIdentity` discriminator; `kind`
  is `existing` (with `existing_provider_id`) or `new` (with
  proposed name and URLs)
- `proposed_env_var_name` — the env var the agent suggests by
  convention (e.g., `ALPHAVANTAGE_API_KEY`)
- `proposed_auth_scheme` — one of the `AuthScheme` enum values
  (`BEARER_HEADER`, `QUERY_PARAM`, `HEADER_CUSTOM`, `BASIC_AUTH`,
  `NONE`)
- `inferred_rate_limit` — JSONB with `requests_per_minute`,
  `requests_per_hour`, `requests_per_day`, `tier_label`, `notes`,
  all nullable. Whatever the agent could read from provider docs.
- `evidence_url` — provider's authentication documentation URL
- `evidence_snippet` — quoted text from `evidence_url` establishing
  that authentication is required
- `rationale` — one line, ≤200 characters, referencing the evidence

Proposals with missing `evidence_url` or `evidence_snippet` are
**dropped before the gap signal is set on graph state**. The
`research` role then falls back to: attempt the probe without a
credential, record the response, and continue research with whatever
shape the response reveals. If subsequent probes also fail with
401/403, the agent records the pattern in `source_summary` for human
review at Gate 1 rather than emitting a gap.

The drop-on-missing-evidence rule means the agent does the same
amount of investigative work either way. The only difference between
"real gap" and "lazy gap" is whether the work yields an escalation or
a documented coercion.

### Anti-patterns (never proposable as gaps)

The following are anti-patterns and never justify a
`CredentialGapProposal`, regardless of how the agent would phrase the
rationale:

- **Ambiguous provider docs.** "Authentication may be required for
  some endpoints" is not evidence. The agent tries without a key,
  observes the response, and decides from the probe. The probe is
  the truth.
- **Transient probe failures.** 5xx errors, network errors, and
  rate-limit 429s are not credential issues. Retry per the v1
  retry policy. Escalate to a gap only on persistent 401 or 403.
- **Provider has a key page but the data is also public.** Many
  providers offer demo or limited-tier keyless access. If the data
  is reachable without a key, do not emit a gap.
- **Pattern-matching on provider name or type.** "This is a vendor,
  so it probably needs a key." Not evidence. Vendors vary; some
  expose public APIs, some don't. Read the docs.
- **Env var exists but probe fails.** Probably a key rotation, quota
  exhaustion, or rotated permissions. Surface as a research error
  with the response body recorded, not as a gap. The operator
  decides whether to rotate or update the credential; that decision
  is normal admin work, not gap escalation.
- **Drafter uncertainty about the auth scheme.** Uncertainty is not
  a gap. If the provider docs are unclear whether to send the key as
  a query param or a Bearer header, the agent picks the more likely
  one based on context, attempts the probe, and either succeeds or
  pivots — without pausing the session.
- **Inability to determine the rate limit precisely.** Rate limit
  values are inferred best-effort and operator-confirmed at the
  wait node. Missing rate limits are not a reason to block the
  gap; record `inferred_rate_limit = null` and let the operator
  fill it in.

Every anti-pattern above is a known failure mode where the agent
might pattern-match on "this looks like a credential issue" and emit
an interrupt for nothing. Every false-positive gap costs the
operator an interruption.

### Multi-gap detection in one pass

When `research` finds multiple providers that need credentials in
one session (rare but possible — e.g., investigating cross-provider
hierarchy enrichment), it emits every gap it identifies, not just
the first. The `credential_gap_proposals` field is list-shaped
exactly so multi-gap sessions can be resolved in one operator
pause.

Research should not stop at the first gap; doing so creates
multi-pause sessions ("apply key 1, resume, hit gap 2, apply key 2,
resume…") that erode operator trust.

### The 2-option picker and the no-override stance

At `credential_gap_wait`, the picker offers only **Apply later
(pause)** and **Abort**. There is no third "Decline and override"
option.

The reason for the asymmetry with enum-gap (which has Apply / Decline
and coerce / Abort) is that the probe is ground truth for
credentials. If the operator believes no key is needed despite the
agent's evidence, the cheapest test is to pick `Apply later` with the
env var deliberately left unset; on resume the probe runs without a
key and either succeeds (proving the operator right) or fails
(proving the agent right). The picker doesn't have to be the place
that decision is made because the probe makes it for them.

If a real "this provider is public" disagreement surfaces in chat,
it travels through chat-level Request changes — operator types "I
think this provider is public; re-research without assuming a key",
research re-runs with an `assume_no_credential` hint, and the probe
decides.

On `Abort`, the operator must type a free-text rationale before the
picker accepts the choice. The rationale is recorded in
`change_proposals` for audit.

### Verification on resume

On resume, `credential_gap_wait` re-runs the probe for each pending
proposal using the env var present in `os.environ`. Four cases:

1. **Probe succeeds.** Record `outcome = provisioned`. Populate the
   `applied_*` fields from the confirmed config (env var name, auth
   scheme, rate limit). Flip audit row to
   `validation_status = applied_by_operator`.
2. **Env var is unset.** The operator may have used a different env
   var name than proposed. Re-render with: "Probe with
   `<proposed_env_var_name>` failed (env var not set). Did you use a
   different env var name? If so, type it in chat." On chat reply
   with a new name, re-probe. On success, record
   `outcome = provisioned_renamed` and
   `applied_env_var_name = <the new name>`.
3. **Probe fails 401 or 403.** The credential is wrong or
   insufficient. Re-render the picker with "Probe failed: 401/403"
   so the operator can rotate, paste a new env var name, or abort.
4. **Probe fails transient (5xx, network).** Retry per the v1 retry
   policy. On exhaustion, surface as a research error and re-render
   the picker with the error context so the operator can decide
   whether to retry resume, try a different env var, or abort.

All gaps must reach a terminal outcome (`provisioned`,
`provisioned_renamed`, `declined`, or `aborted`) before research can
complete and the graph can advance. Partial resolution across
multiple resumes is fine.

### The drafter does not write the credential to anything but state

The credential value (the key string) never enters macrodb, never
enters `change_proposals`, never enters graph state, never enters
logs. The agent reads it from `os.environ` at probe time and passes
it to the HTTP client. Both the probe code and the ingestion runtime
use the same pattern. The audit row records the **env var name**,
not the value.

There is no field for the credential value in
`CredentialGapProposal` or `CredentialGapResolution`. The absence is
the enforcement.

### Examples of legitimate gaps

These are reference examples for "this is what a real gap looks like".
They are not anchors for new gap emission; the discipline above is.

- A provider is Alpha Vantage. The agent probes
  `https://www.alphavantage.co/query?function=REAL_GDP&apikey=demo`
  and receives 200 OK with a payload containing
  `"Information": "Thank you for using Alpha Vantage! ... claim
  your free API key"`. The docs at
  `https://www.alphavantage.co/support/#api-key` confirm that all
  productive use requires a key. Real gap; proposed env var
  `ALPHAVANTAGE_API_KEY`; `QUERY_PARAM` scheme; rate limit 25/day
  on demo tier.
- A provider is the U.S. Census Bureau's API. The agent probes a
  representative ACS endpoint without a key and receives a 403 with
  body `"A valid key must be included with each data API request."`
  Docs at `https://api.census.gov/data/key_signup.html` confirm.
  Real gap; proposed env var `CENSUS_API_KEY`; `QUERY_PARAM` scheme;
  rate limits not explicitly published, so `inferred_rate_limit`
  records null.
- A provider is OECD's data API on an endpoint that requires a
  subscription key for a specific dataset. Probe returns 401 with a
  body pointing at the subscription page. Real gap.

### Examples of non-gaps (look like gaps; aren't)

- A probe against the World Bank's WDI API returns 200 OK without a
  key. The WB key page exists but is for higher-quota usage. Not a
  gap; proceed without a key and record the public-access pattern.
- A probe against a FRED endpoint returns 200 OK because the
  operator already provisioned `FRED_API_KEY` in a previous
  session. Pre-check passes at layer 3. No gap is emitted; the
  session continues using the env var.
- A probe returns 503 Service Unavailable repeatedly. Not a
  credential issue. Retry per the v1 retry policy; on exhaustion,
  surface as a research error, not as a gap.
- A probe returns 429 Too Many Requests. Not a credential issue
  even if the operator's key is real; the provider is rate-limiting
  the IP. Surface as a research error with a recorded rate-limit
  signal so the operator can pace future research.

## Notes for the reader of this skill

- The asymmetry between conditions (all three required) and
  anti-patterns (any one disqualifies) is deliberate. The bar is
  high because every false-positive gap is an operator interruption
  in a session that was supposed to be doing investigative work.
- This skill composes with `skill-enum-gap-escalation`. If a
  provider's auth scheme falls outside the closed `AuthScheme` enum,
  the agent first emits an `EnumGapProposal` against `AuthScheme`,
  the operator widens the enum, and only then can the
  `CredentialGapProposal` carry the (now-supported) auth scheme.
- The pre-check is load-bearing. Without it, the agent would
  re-emit gaps for credentials the operator had already
  provisioned, exhausting trust quickly. The cache also matters: a
  research phase that probes many endpoints of the same provider
  must not pay the pre-check cost per endpoint.
- The audit row preserves what the operator did, not whether the
  session succeeded. If the operator provisions a credential and
  then the session aborts at Gate 1 for unrelated reasons, the
  credential setup is still real and the audit row reflects that.
  The next session against the same provider sees the provisioning
  via the pre-check and does not ask again.
