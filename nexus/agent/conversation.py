"""Bounded, in-memory conversation orchestration."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import closing

from nexus.config import Settings
from nexus.agent.memory import ConversationMemory
from nexus.models.base import ChatProvider
from nexus.models.ollama_provider import ProviderError


class ConversationError(ValueError):
    """Raised for invalid conversation input or an empty model response."""


class Conversation:
    """Keep a bounded recent transcript and commit only complete replies."""

    def __init__(self, provider: ChatProvider, settings: Settings):
        self._provider = provider
        self._settings = settings
        self._memory = ConversationMemory(settings.memory_db_path)
        saved = self._memory.list_conversations()
        self._session_id = str(saved[0]["id"]) if saved else self._memory.create_conversation()
        loaded = self._memory.load(self._session_id)
        self._history = self._bounded(loaded)
        if self._history != loaded:
            self._memory.save(self._session_id, self._history)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def title(self) -> str:
        return self._memory.title(self._session_id)

    def saved_conversations(self) -> list[dict[str, str | int]]:
        return self._memory.list_conversations()

    def new_conversation(self) -> str:
        self._session_id = self._memory.create_conversation()
        self._history = []
        return self._session_id

    def select_conversation(self, session_id: str) -> None:
        # Read before switching so a database error leaves the visible chat intact.
        self._memory.title(session_id)
        loaded = self._memory.load(session_id)
        self._session_id = session_id
        self._history = self._bounded(loaded)
        if self._history != loaded:
            self._memory.save(session_id, self._history)

    def delete_conversation(self, session_id: str) -> None:
        self._memory.delete(session_id)
        if session_id == self._session_id:
            saved = self._memory.list_conversations()
            self._session_id = str(saved[0]["id"]) if saved else self._memory.create_conversation()
            self._history = self._bounded(self._memory.load(self._session_id))

    @property
    def history(self) -> tuple[Mapping[str, str], ...]:
        """A read-only snapshot of the current transcript."""
        return tuple(dict(message) for message in self._history)

    def clear(self) -> None:
        self._memory.clear(self._session_id)
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
        completed = self._bounded([*pending, {"role": "assistant", "content": answer}])
        self._memory.save(self._session_id, completed)
        self._history = completed
