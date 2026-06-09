# Skills

Domain knowledge packs used by the gated onboarding agent (ADR 0011). Each
skill is a small Markdown document covering one bounded piece of macrodb
domain expertise. Skills are lazy-loaded into LLM context per call, driven
by state-side triggers, not statically per role.

## Why skills exist

The agent's roles (researcher, three reviewers, drafters, executor) each
have a base system prompt that describes their job. Loading "everything
about macrodb" into every node's prompt would bloat context, hide weak
signals, and confuse the model when the task at hand only needs a narrow
slice of knowledge.

Skills solve this by letting each node pull only the domain context its
current state actually needs. A node working on a candidate hierarchy
enrichment loads `skill-hierarchy-edge-proposal` plus
`skill-concept-vs-family-vs-variant`. A node working on a flat single-series
onboarding loads neither.

## Skill contract

Each skill is a Markdown file at `docs/skills/<skill-id>.md`. Required
sections:

- **Status.** `stub`, `draft`, or `accepted`. Stubs are placeholders; the
  scope is fixed but the body is not yet written. Accepted skills have been
  reviewed and can be loaded by the runtime.
- **Scope.** One paragraph describing what knowledge this skill covers and
  the boundary against neighboring skills.
- **When triggered.** Concrete state predicates that should load this skill:
  what fields, what values, what node calls it from.
- **Body.** Domain knowledge content — rules, examples, edge cases. This is
  what gets prepended to the LLM prompt. Domain knowledge only; never
  procedural instructions ("first do X, then Y"). Orchestration is the
  graph's job.

## Loading rules

A node declares a `skill_triggers` map of `(state_predicate, skill_id)`
pairs. Before each LLM call, the node walks the triggers, evaluates each
predicate against current graph state, and assembles the prompt as
`base_role_prompt + selected_skill_bodies`.

The `loaded_skills` field in graph state records every skill load event for
eval. After a session, you can ask "did the researcher have the hierarchy
skill loaded when it proposed that edge?" and the answer is unambiguous.

A skill that is not currently in `accepted` status must not be loaded by the
runtime. A stub or draft skill is documentation, not behavior.

## Skill inventory (v1)

| Skill | Status | Domain |
|---|---|---|
| [skill-series-source-ingestion-feed-linking](skill-series-source-ingestion-feed-linking.md) | stub | When an existing `ingestion_feed` covers a new `series_source` vs. when a new feed is required |
| [skill-hierarchy-edge-proposal](skill-hierarchy-edge-proposal.md) | stub | Evaluating candidate parent-child `series` relationships |
| [skill-concept-vs-family-vs-variant](skill-concept-vs-family-vs-variant.md) | stub | The boundary rules from `docs/series_catalog_governance.md` |
| [skill-canonical-code-grammar](skill-canonical-code-grammar.md) | stub | The `<geo>_<concept>_<variant?>_<freq>_<sa>_<measure>` slot grammar |
| [skill-provider-locator-quality](skill-provider-locator-quality.md) | stub | Assessing `external_code` and `ref_url` quality |
| [skill-ambiguity-handling](skill-ambiguity-handling.md) | stub | The "ambiguity stays in proposal space" rule |
| [skill-dangerous-correction](skill-dangerous-correction.md) | stub | When and how Gate 2 is triggered |
| [skill-first-run-policy](skill-first-run-policy.md) | stub | Tolerated warnings vs. hard failures for the first ingestion |
| [skill-macro-research-discipline](skill-macro-research-discipline.md) | stub | What to search for and verify when investigating a new source |
| [skill-ingestion-selector-conventions](skill-ingestion-selector-conventions.md) | stub | The selector contract, conventions, and review criteria |
| [skill-generic-runtime-selectors](skill-generic-runtime-selectors.md) | stub | Which selector_types currently exist and which provider shapes they cover |

## Authoring a new skill

1. Add a new file `docs/skills/skill-<short-id>.md` with the required
   sections; start at `status: stub`.
2. Add a row to the inventory table above.
3. Write the body when you next need that knowledge to be loadable, not
   speculatively. A stub is fine forever if no one needs it; a half-written
   draft is worse than an honest stub.
4. Promote to `accepted` only after a reviewer (governance or selector,
   depending on domain) has confirmed the content and the trigger predicates
   match what the loader actually evaluates.

Skills should remain narrow. If a skill grows past ~150 lines of body
content, it is probably two skills that should be split.
