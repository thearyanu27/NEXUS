"""Provider-neutral message and model interfaces."""

from __future__ import annotations

from typing import Iterable, Iterator, Mapping, Protocol, TypedDict


class ChatMessage(TypedDict):
    role: str
    content: str


class ChatProvider(Protocol):
    def stream_chat(self, messages: Iterable[Mapping[str, str]]) -> Iterator[str]:
        """Yield response text chunks for a sequence of chat messages."""
        ...
