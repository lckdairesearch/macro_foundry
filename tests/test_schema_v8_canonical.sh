#!/usr/bin/env bash
# Acceptance tests for issue #77: V8 schema promoted to canonical (db_er.txt).
# Each check prints PASS or FAIL. Exit code is the count of failures.

SCHEMA="docs/schema/db_er.txt"
FAIL=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

# ── Criterion 1: header says V8, not V7 ─────────────────────────────────────

grep -q "Schema V8" "$SCHEMA" \
  && pass "db_er.txt header reads 'Schema V8'" \
  || fail "db_er.txt header still reads 'Schema V7' (or missing V8 marker)"

grep -q "Schema V7" "$SCHEMA" \
  && fail "db_er.txt still contains 'Schema V7' string" \
  || pass "db_er.txt has no 'Schema V7' string"

# ── Criterion 2: collapsed tables are absent ─────────────────────────────────

for tbl in concepts indicators indicator_variants tags concept_tags; do
  grep -q "^${tbl} \[" "$SCHEMA" \
    && fail "db_er.txt still defines table: $tbl" \
    || pass "db_er.txt has no table definition for: $tbl"
done

# ── Criterion 3: V8 tables are present ───────────────────────────────────────

for tbl in categories category_edges source_groups source_group_members; do
  grep -q "^${tbl} \[" "$SCHEMA" \
    && pass "db_er.txt defines table: $tbl" \
    || fail "db_er.txt missing table definition for: $tbl"
done

# series must carry the new columns
grep -q "category_id" "$SCHEMA" \
  && pass "db_er.txt series has category_id column" \
  || fail "db_er.txt series missing category_id column"

grep -q "is_default" "$SCHEMA" \
  && pass "db_er.txt series has is_default column" \
  || fail "db_er.txt series missing is_default column"

echo ""
echo "Result: $FAIL failure(s)"
exit $FAIL
