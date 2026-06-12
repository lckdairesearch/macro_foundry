import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage


ONBOARDING_AGENT_DIR = Path(__file__).resolve().parents[2] / "src" / "macro_foundry" / "onboarding_agent"
if str(ONBOARDING_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(ONBOARDING_AGENT_DIR))


@pytest.mark.no_db
def test_series_brief_clarification_routes_back_to_clarifier(monkeypatch):
    import onboarding_scope

    calls: list[str] = []

    class FakeStructuredModel:
        def __init__(self, schema):
            self.schema = schema

        def invoke(self, _messages):
            if self.schema.__name__ == "ClarifyWithUser":
                calls.append("clarify_with_user")
                if calls.count("clarify_with_user") == 1:
                    return SimpleNamespace(
                        need_clarification=False,
                        question="",
                        verification="I have enough to write the brief.",
                    )
                return SimpleNamespace(
                    need_clarification=True,
                    question="Which exact FRED series code should macrodb onboard?",
                    verification="",
                )

            calls.append("write_series_brief")
            return SimpleNamespace(
                series_brief="",
                needs_clarification=True,
                clarification_question="Which exact FRED series code should macrodb onboard?",
                clarification_reasons=["US CPI from FRED has multiple plausible variants."],
            )

    class FakeModel:
        def with_structured_output(self, schema, tools=None):
            return FakeStructuredModel(schema)

    monkeypatch.setattr(onboarding_scope, "get_model", lambda: FakeModel())

    result = onboarding_scope.scope_series_onboarding.invoke(
        {"messages": [HumanMessage(content="Onboard US CPI from FRED")]}
    )

    assert calls == ["clarify_with_user", "write_series_brief", "clarify_with_user"]
    assert result["series_brief"] == ""
    assert result["need_clarification"] is True
    assert result["clarification_question"] == "Which exact FRED series code should macrodb onboard?"
    assert result["clarification_reasons"] == ["US CPI from FRED has multiple plausible variants."]
    assert result["messages"][-1].content == "Which exact FRED series code should macrodb onboard?"
