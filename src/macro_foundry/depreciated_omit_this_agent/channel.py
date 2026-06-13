"""Typed channel interface for onboarding clients."""

from __future__ import annotations

from typing import Protocol

import questionary
from pydantic import BaseModel, ConfigDict
from rich.console import Console


class ChannelEvent(BaseModel):
    """Rendered output event emitted by the onboarding graph."""

    model_config = ConfigDict(frozen=True)

    text: str


class ChannelPrompt(BaseModel):
    """Typed prompt sent to a human-facing channel implementation."""

    model_config = ConfigDict(frozen=True)

    text: str


class ChannelResponse(BaseModel):
    """Typed response returned by a channel implementation."""

    model_config = ConfigDict(frozen=True)

    text: str


class Channel(Protocol):
    """I/O seam between the graph and a concrete client."""

    async def emit(self, event: ChannelEvent) -> None:
        """Render an event to the client."""

    async def prompt(self, prompt: ChannelPrompt) -> ChannelResponse:
        """Ask the client for the next input."""


class RichQuestionaryChannel:
    """Terminal channel backed by Rich rendering and Questionary input."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    async def emit(self, event: ChannelEvent) -> None:
        self._console.print(event.text)

    async def prompt(self, prompt: ChannelPrompt) -> ChannelResponse:
        answer = await questionary.text(prompt.text).unsafe_ask_async()
        return ChannelResponse(text=answer or "/save")


__all__ = [
    "Channel",
    "ChannelEvent",
    "ChannelPrompt",
    "ChannelResponse",
    "RichQuestionaryChannel",
]
