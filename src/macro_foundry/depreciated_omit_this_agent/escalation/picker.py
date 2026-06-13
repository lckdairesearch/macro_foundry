"""Questionary picker helpers for escalation wait nodes."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

import questionary
from pydantic import BaseModel, ConfigDict
from rich.console import Console


class PickerOutcome(str, Enum):
    """Structured escalation picker outcomes."""

    APPLY_LATER = "apply_later"
    DECLINE_AND_COERCE = "decline_and_coerce"
    ABORT = "abort"


class EscalationPickerOption(BaseModel):
    """One selectable human action in an escalation picker."""

    model_config = ConfigDict(frozen=True)

    label: str
    outcome: PickerOutcome


class OperatorInstructionBlock(BaseModel):
    """Inline instructions rendered above the picker."""

    model_config = ConfigDict(frozen=True)

    title: str
    body: str

    @classmethod
    def from_template(
        cls,
        *,
        title: str,
        template: str,
        values: dict[str, Any],
    ) -> "OperatorInstructionBlock":
        """Build an instruction block from a named format-string template."""

        return cls(
            title=title,
            body=template.format(**{key: str(value) for key, value in values.items()}),
        )

    def render(self) -> str:
        """Render the block as terminal text."""

        return f"{self.title}\n{self.body}"


class EscalationPickerResult(BaseModel):
    """Structured result returned by the picker."""

    model_config = ConfigDict(frozen=True)

    label: str
    outcome: PickerOutcome


class _QuestionaryPrompt(Protocol):
    async def unsafe_ask_async(self) -> str | None:
        """Return the selected choice label."""


class _QuestionaryModule(Protocol):
    def select(self, message: str, *, choices: list[str]) -> _QuestionaryPrompt:
        """Build a Questionary select prompt."""


class _Console(Protocol):
    def print(self, text: str) -> None:
        """Render terminal text."""


async def render_escalation_picker(
    *,
    prompt: str,
    options: tuple[EscalationPickerOption, ...],
    instruction_blocks: tuple[OperatorInstructionBlock, ...] = (),
    questionary_module: _QuestionaryModule = questionary,
    console: _Console | None = None,
) -> EscalationPickerResult:
    """Render instructions and ask the operator for a structured escalation action."""

    if len(options) not in {2, 3}:
        raise ValueError("escalation pickers support exactly 2 or 3 options")

    active_console = console or Console()
    for block in instruction_blocks:
        active_console.print(block.render())

    options_by_label = {option.label: option for option in options}
    selected_label = await questionary_module.select(
        prompt,
        choices=list(options_by_label),
    ).unsafe_ask_async()
    if selected_label is None:
        selected_label = next(iter(options_by_label))
    selected = options_by_label[selected_label]
    return EscalationPickerResult(label=selected.label, outcome=selected.outcome)


__all__ = [
    "EscalationPickerOption",
    "EscalationPickerResult",
    "OperatorInstructionBlock",
    "PickerOutcome",
    "render_escalation_picker",
]
