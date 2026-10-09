"""Bounded, in-memory conversation orchestration."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import closing

from nexus.config import Settings
from nexus.models.base import ChatProvider
from nexus.models.ollama_provider import ProviderError


class ConversationError(ValueError):
    """Raised for invalid conversation input or an empty model response."""


class Conversation:
    """Keep a bounded recent transcript and commit only complete replies."""

    def __init__(self, provider: ChatProvider, settings: Settings):
        self._provider = provider
        self._settings = settings
        self._history: list[dict[str, str]] = []

    @property
    def history(self) -> tuple[Mapping[str, str], ...]:
        """A read-only snapshot of the current transcript."""
        return tuple(dict(message) for message in self._history)

    def clear(self) -> None:
        self._history.clear()

    def _bounded(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        limit = self._settings.max_history_messages
        if len(messages) <= limit:
            return messages
        # Drop old whole turns where possible; never begin context with an assistant turn.
        kept = messages[-limit:]
        if kept and kept[0]["role"] == "assistant":
            kept = kept[1:]
        return kept

    def stream_reply(self, prompt: str) -> Iterator[str]:
        """Yield model output and save the exchange only after a full response."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ConversationError("Please enter a message first.")
        prompt = prompt.strip()
        if len(prompt) > self._settings.max_message_chars:
            raise ConversationError(
                f"That message is over the {self._settings.max_message_chars:,}-character limit."
            )

        pending = self._bounded([*self._history, {"role": "user", "content": prompt}])
        chunks: list[str] = []
        response_length = 0
        try:
            with closing(self._provider.stream_chat(pending)) as stream:
                for chunk in stream:
                    if not isinstance(chunk, str):
                        raise ProviderError("The model provider returned invalid response text.")
                    chunks.append(chunk)
                    response_length += len(chunk)
                    if response_length > self._settings.max_message_chars * 2:
                        raise ProviderError("The model response exceeded the configured size limit.")
                    yield chunk
        except BaseException:
            # A failed or cancelled turn does not pollute the saved transcript.
            raise
        answer = "".join(chunks).strip()
        if not answer:
            raise ConversationError("The model returned an empty response. Please try again.")
        self._history = self._bounded([*pending, {"role": "assistant", "content": answer}])
