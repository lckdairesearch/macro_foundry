#!/usr/bin/env bash
# Acceptance tests for issue-71: docs terminology sweep (series_family → indicator).
# Each check prints PASS or FAIL. Exit code is the count of failures.

FAIL=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

# ── CONTEXT.md ──────────────────────────────────────────────────────────────

grep -q "^### Indicator$" CONTEXT.md \
  && pass "CONTEXT.md has '### Indicator' heading" \
  || fail "CONTEXT.md missing '### Indicator' heading"

grep -q "^### Indicator variant$" CONTEXT.md \
  && pass "CONTEXT.md has '### Indicator variant' heading" \
  || fail "CONTEXT.md missing '### Indicator variant' heading"

grep -qi "is_default" CONTEXT.md \
  && pass "CONTEXT.md documents is_default" \
  || fail "CONTEXT.md missing is_default documentation"

grep -q "series_family_members" CONTEXT.md \
  && fail "CONTEXT.md still references series_family_members" \
  || pass "CONTEXT.md has no series_family_members"

grep -q "series_family[^_]" CONTEXT.md \
  && fail "CONTEXT.md still references series_family" \
  || pass "CONTEXT.md has no series_family references"

# ── ADR 0008 ─────────────────────────────────────────────────────────────────

grep -q "series_family_members" docs/adr/0008-foreign-key-delete-policy.md \
  && fail "ADR 0008 still references series_family_members" \
  || pass "ADR 0008 has no series_family_members"

grep -q "indicator_variants" docs/adr/0008-foreign-key-delete-policy.md \
  && pass "ADR 0008 references indicator_variants" \
  || fail "ADR 0008 missing indicator_variants"

# ── ADR 0013 ─────────────────────────────────────────────────────────────────

grep -q "series_family_members" docs/adr/0013-metadata-standardisation.md \
  && fail "ADR 0013 still references series_family_members" \
  || pass "ADR 0013 has no series_family_members"

grep -q "series_family[^_]" docs/adr/0013-metadata-standardisation.md \
  && fail "ADR 0013 still references series_family" \
  || pass "ADR 0013 has no series_family references"

# ── series_catalog_governance.md ─────────────────────────────────────────────

grep -q "series_family_members" docs/series_catalog_governance.md \
  && fail "series_catalog_governance.md still references series_family_members" \
  || pass "series_catalog_governance.md has no series_family_members"

grep -qi "indicator" docs/series_catalog_governance.md \
  && pass "series_catalog_governance.md references indicator" \
  || fail "series_catalog_governance.md missing indicator"

# ── skill docs ───────────────────────────────────────────────────────────────

grep -q "series_family_members" docs/skills/skill-concept-vs-family-vs-variant.md \
  && fail "skill-concept-vs-family-vs-variant.md still references series_family_members" \
  || pass "skill-concept-vs-family-vs-variant.md has no series_family_members"

grep -q "series_family_members" docs/skills/skill-metadata-standardisation.md \
  && fail "skill-metadata-standardisation.md still references series_family_members" \
  || pass "skill-metadata-standardisation.md has no series_family_members"

grep -q "series_family[^_]" docs/skills/skill-metadata-standardisation.md \
  && fail "skill-metadata-standardisation.md still references series_family" \
  || pass "skill-metadata-standardisation.md has no series_family references"

# ── build_plan.md ─────────────────────────────────────────────────────────────

grep -q "series_family_members" docs/build_plan.md \
  && fail "build_plan.md still references series_family_members" \
  || pass "build_plan.md has no series_family_members"

# ── code_standards.md ────────────────────────────────────────────────────────

grep -q "series_family_members" docs/code_standards.md \
  && fail "code_standards.md still references series_family_members" \
  || pass "code_standards.md has no series_family_members"

# ── CLAUDE.md + AGENTS.md ────────────────────────────────────────────────────

grep -q "series_family" CLAUDE.md \
  && fail "CLAUDE.md still references series_family" \
  || pass "CLAUDE.md has no series_family"

grep -q "series_family" AGENTS.md \
  && fail "AGENTS.md still references series_family" \
  || pass "AGENTS.md has no series_family"

# ── series_onboarding_workflow.md ─────────────────────────────────────────────

grep -q "series_family_members" docs/series_onboarding_workflow.md \
  && fail "series_onboarding_workflow.md still references series_family_members" \
  || pass "series_onboarding_workflow.md has no series_family_members"

grep -q "series_family[^_]" docs/series_onboarding_workflow.md \
  && fail "series_onboarding_workflow.md still references series_family" \
  || pass "series_onboarding_workflow.md has no series_family references"

# ── progress_tracker.md ──────────────────────────────────────────────────────

grep -q "Issue 71\|issue 71\|issue-71\|#71" docs/progress_tracker.md \
  && pass "progress_tracker.md has a #71 entry" \
  || fail "progress_tracker.md missing #71 entry"

grep -q "ADR 0021\|0021" docs/progress_tracker.md \
  && pass "progress_tracker.md references ADR 0021" \
  || fail "progress_tracker.md missing reference to ADR 0021 in #71 entry"

echo ""
echo "Result: $FAIL failure(s)"
exit $FAIL
