from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def read_doc(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


@pytest.mark.no_db
def test_issue_12_architecture_decision_is_ratified_in_docs() -> None:
    adr = read_doc("docs/adr/0010-request-level-ingestion-and-series-hierarchy.md")

    assert "request-level ingestion" in adr
    assert "ingestion_feed_member" in adr
    assert "ingestion_run_log_member" in adr
    assert "member-level provenance" in adr
    assert "hidden canonical placeholder" in adr
    assert "source-centric feeds" in adr

    adr_index = read_doc("docs/adr/README.md")
    assert "0010" in adr_index
    assert "Request-level ingestion and canonical series hierarchy" in adr_index

    glossary = read_doc("CONTEXT.md")
    assert "An ingestion feed is the runtime configuration for one upstream request" in glossary
    assert "series_source_id" not in glossary.partition("### Ingestion feed")[2].partition("### Ingestion run log")[0]
    assert "Ingestion feed member" in glossary
    assert "Ingestion run log member" in glossary

    architecture = read_doc("docs/architecture.md")
    assert "request-level execution unit" in architecture
    assert "member-level provenance" in architecture

    build_plan = read_doc("docs/build_plan.md")
    assert "request-level ingestion" in build_plan
    assert "canonical series hierarchy" in build_plan
    assert "Series composition trees" not in build_plan

    project_overview = read_doc("docs/project_overview.md")
    assert "Hierarchical composition trees" not in project_overview

    progress = read_doc("docs/progress_tracker.md")
    assert "Issue 12" in progress
    assert "reopened hierarchy work" in progress
