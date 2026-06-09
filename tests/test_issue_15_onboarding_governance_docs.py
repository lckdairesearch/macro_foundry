from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read_doc(relative_path: str) -> str:
    return " ".join((ROOT / relative_path).read_text().split())


@pytest.mark.no_db
def test_issue_15_onboarding_and_governance_rules_are_documented() -> None:
    onboarding = read_doc("docs/series_onboarding_workflow.md")
    governance = read_doc("docs/series_catalog_governance.md")
    fred_plan = read_doc("docs/fred_bootstrap_plan.md")
    progress = read_doc("docs/progress_tracker.md")

    assert "Hierarchy enrichment review" in onboarding
    assert "additive hierarchy enrichment" in onboarding
    assert "same-concept default" in onboarding
    assert "cross-concept hierarchy proposal" in onboarding
    assert "weak provider locator" in onboarding
    assert "missing `external_code`" in onboarding
    assert "missing `ref_url`" in onboarding
    assert "Routine refreshes must not create, delete, or rewrite `series_hierarchy_edges`" in onboarding
    assert "explicit onboarding or approved repair flow" in onboarding

    assert "Hierarchy governance" in governance
    assert "additive hierarchy enrichment" in governance
    assert "same-concept edges" in governance
    assert "human review" in governance
    assert "hidden placeholder canonical series" in governance
    assert "Weak provider locator governance" in governance

    assert "Routine FRED refreshes must not mutate hierarchy structure" in fred_plan
    assert "structural changes belong in onboarding or approved repair workflows" in fred_plan

    assert "Issue 15" in progress
    assert "weak provider locators" in progress
