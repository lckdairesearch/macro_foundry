# ADR 0018 — Scoping subgraph splits clarify, verify, and brief authoring into separate nodes

**Status:** Accepted

**Date:** 2026-06-12

## Context

The onboarding scoping prototype in `src/macro_foundry/onboarding_agent/1_scoping.ipynb` started as a two-node LangGraph:

- `clarify_with_user` — decides whether the user has provided enough information to identify the target series. If not, asks a question and ends. If yes, hands off to the brief writer.
- `write_series_brief` — writes the onboarding handoff brief. The brief writer also voted on whether more clarification was needed, with a back-edge that routed back to `clarify_with_user` on failure.

In practice, the brief writer caught failure modes that the clarifier did not, because the brief writer did deeper web research as a side effect of authoring. The motivating case: a user requests "headline inflation FRED CPILFESL." The clarifier passes — provider + ticker is unambiguous on its face — but `CPILFESL` is core CPI, not headline. The brief writer surfaces the conflict only because authoring forces it to look up the canonical meaning.

This produced two coupled problems:

- Two nodes voted on the same `needs_clarification` decision with two different prompts. The clarifier's six-criterion prompt and the brief writer's authoring prompt can disagree on edge cases, and there is no clean way to make them agree without growing both prompts.
- The brief writer was doing two jobs: writing the artifact and gating on user-info sufficiency. The first job is its responsibility; the second belongs to the clarifier.

The single-responsibility lens points at a third concern hiding inside the brief writer: verifying that the user's identifier matches their description. That verification is what catches CPILFESL/headline, and it is neither a completeness check nor an authoring step.

## Decision

The scoping subgraph is restructured into three nodes with one responsibility each, plus a bounded back-edge for conflict resolution.

**Topology.**

```
START -> clarify_with_user -> verify_identifier -> write_series_brief -> END
              ^                       |
              |_______________________|
                (bounded by MAX_VERIFICATION_ATTEMPTS = 2)
```

- `clarify_with_user` owns **completeness**. Reads `messages` and an optional `verification_conflict`. If the conflict slot is non-empty, the question targets that conflict and bypasses the general criteria. Otherwise, it applies four identification criteria. Output: either a user-facing question (ends the turn) or a verification message (proceeds to verify).
- `verify_identifier` owns **identifier-vs-description verification**. Reads `messages`. Uses `web_search` to check the canonical meaning of the identifier against the user's description. Outputs `has_conflict`, `conflict_description`, and `findings` (canonical name, source URL, short notes). Routes back to `clarify_with_user` with the conflict context on mismatch, up to `MAX_VERIFICATION_ATTEMPTS = 2`. After the cap, proceeds to brief authoring with the unresolved conflict surfaced in state.
- `write_series_brief` owns **authoring**. Reads `messages` and `verification_findings` as authoritative. Fills remaining gaps via targeted `web_search`. Does not gate, vote, or ask for clarification.

**State namespacing.** State fields are namespaced per node so responsibilities do not leak:

- `clarify_with_user`: `need_clarification`, `clarification_question`, `clarification_reasons`.
- `verify_identifier`: `verification_findings`, `verification_conflict`, `verification_attempts`.
- `write_series_brief`: `series_brief`.

**Prompt boundaries.** The clarifier's old criteria 5 (acronym clarification) and 6 (identifier/description conflict handling) are removed. Conflict handling moves wholly into `verify_identifier`. The brief writer's trailing `needs_clarification` block is removed; the brief writer never gates.

**Loop bound.** The verify → clarify back-edge is capped at two retries. After the cap, the graph proceeds to the brief writer with the conflict marked as unresolved rather than asking the user a third time.

**Tool sharing without responsibility sharing.** Both `verify_identifier` and `write_series_brief` may call `web_search`, but for different queries: verify tests a conflict hypothesis; the brief writer enriches attributes. The verifier's `findings` field is passed forward so the brief writer does not redo identical searches. The verifier must not drift into full attribute collection.

## Consequences

**Positive:**

- One source of truth for `needs_clarification`. The clarifier is the sole gatekeeper; the verifier cannot send the user back for any reason except a specific, named conflict.
- Each node is testable in isolation against a small input/output contract.
- The CPILFESL/headline failure case is now caught at the node whose job it is, with a question that targets the conflict rather than re-running general criteria.
- Authoring is decoupled from gating, so the brief writer prompt shrinks and reads as authoring instructions only.
- The downstream `check_db` dedup node planned for the next scoping milestone operates on a verified, trustworthy identifier rather than a possibly-wrong ticker.

**Negative:**

- One additional node and one additional prompt to maintain.
- An additional LLM call in the happy path, even when the input is unambiguous. Cost is small for short identifier strings and is acceptable for the correctness gain.
- Two prompts (clarify, brief author) now consume an extra placeholder each (`{verification_conflict}`, `{verification_findings}`), which the orchestration must always pass.

**Neutral:**

- Notebook source-of-truth pattern is preserved. `state_scope.py` and `onboarding_scope.py` are generated by `%%writefile` cells in `1_scoping.ipynb`. `prompts.py` is edited directly. Commits include the `.ipynb` and the regenerated `.py` together.

## Alternatives considered

- **Status quo: keep the brief writer doubling as gate.** Rejected because two prompts continued to vote on the same boolean, the brief writer mixed two jobs, and the loop had no cap.
- **Collapse: trust the clarifier as the sole gate, no back-edge.** Rejected for this prototype because the clarifier cannot reliably catch identifier/description conflicts without doing the same web verification work, which would inflate its prompt and its tool budget on every call (including the easy cases). Verification as a dedicated node is cheaper to reason about.
- **Beef up the clarifier with a verification budget.** Rejected for the same reason as the previous alternative, plus the SRP concern: one prompt covering "is this enough?" and "is this consistent?" reintroduces the drift that motivated this ADR.
- **Self-revise loop inside the brief writer.** Rejected because the right resolution for an identifier/description conflict is a user decision (follow the ticker or the description), not an authoring revision.
- **No loop bound.** Rejected because two stochastic LLM nodes voting on a conflict can disagree indefinitely on edge cases. Capping at two attempts surfaces the conflict to the next stage instead of looping the user.
