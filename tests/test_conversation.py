from __future__ import annotations

import unittest

from nexus.agent.conversation import Conversation, ConversationError
from nexus.config import Settings
from nexus.models.ollama_provider import ProviderError


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.fail = False

    def stream_chat(self, messages):
        self.calls.append([dict(message) for message in messages])
        if self.fail:
            raise ProviderError("offline")
        yield "A "
        yield "reply."


class ConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = FakeProvider()
        self.settings = Settings(max_history_messages=4, max_message_chars=100)
        self.conversation = Conversation(self.provider, self.settings)

    def test_streams_and_saves_complete_turns(self) -> None:
        self.assertEqual("".join(self.conversation.stream_reply("Hello")), "A reply.")
        self.assertEqual([item["role"] for item in self.conversation.history], ["user", "assistant"])

    def test_context_is_bounded_and_starts_on_a_user_turn(self) -> None:
        for prompt in ("one", "two", "three"):
            list(self.conversation.stream_reply(prompt))
        last_request = self.provider.calls[-1]
        self.assertLessEqual(len(last_request), self.settings.max_history_messages)
        self.assertEqual(last_request[0]["role"], "user")

    def test_failure_and_cancellation_do_not_commit_a_turn(self) -> None:
        list(self.conversation.stream_reply("saved"))
        before = self.conversation.history
        self.provider.fail = True
        with self.assertRaises(ProviderError):
            list(self.conversation.stream_reply("failed"))
        self.assertEqual(self.conversation.history, before)
        self.provider.fail = False
        pending = self.conversation.stream_reply("cancelled")
        next(pending)
        pending.close()
        self.assertEqual(self.conversation.history, before)

    def test_input_limits_and_clear(self) -> None:
        with self.assertRaises(ConversationError):
            list(self.conversation.stream_reply("x" * 101))
        with self.assertRaises(ConversationError):
            list(self.conversation.stream_reply("  "))
        list(self.conversation.stream_reply("ok"))
        self.conversation.clear()
        self.assertEqual(self.conversation.history, ())


if __name__ == "__main__":
    unittest.main()
