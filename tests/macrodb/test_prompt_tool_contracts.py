"""Verify prompts.py references current MCP tool names, not stale pre-rename names."""

from __future__ import annotations

import pytest

from macro_foundry.onboarding_agent.prompts import check_db_instructions


@pytest.mark.no_db
def test_check_db_instructions_references_new_tool_names() -> None:
    assert "search_indicators" in check_db_instructions
    assert "lookup_indicator" in check_db_instructions


@pytest.mark.no_db
def test_check_db_instructions_has_no_stale_family_tool_names() -> None:
    assert "lookup_family" not in check_db_instructions
    assert "search_series_families" not in check_db_instructions
