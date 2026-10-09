from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from nexus.config import Settings
from nexus.models.ollama_provider import OllamaProvider, ProviderError


class FakeResponse:
    def __init__(self, data: bytes):
        self._stream = io.BytesIO(data)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def read(self):
        return self._stream.read()

    def __iter__(self):
        return iter(self._stream)

    def close(self):
        self.closed = True
        self._stream.close()


class OllamaProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OllamaProvider(Settings())

    def test_provider_initializes_endpoints_from_configuration(self) -> None:
        self.assertEqual(self.provider.tags_url, "http://127.0.0.1:11434/api/tags")
        self.assertEqual(self.provider.chat_url, "http://127.0.0.1:11434/api/chat")

    @patch("nexus.models.ollama_provider.urlopen")
    def test_health_check_finds_configured_model(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(json.dumps({"models": [{"name": "qwen2.5:7b"}]}).encode())
        status = self.provider.health_check()
        self.assertTrue(status.connected)
        self.assertTrue(status.model_available)

    @patch("nexus.models.ollama_provider.urlopen", side_effect=URLError("refused"))
    def test_health_check_handles_connection_failure(self, _urlopen) -> None:
        status = self.provider.health_check()
        self.assertFalse(status.connected)
        self.assertIn("Could not connect", status.message)

    @patch("nexus.models.ollama_provider.urlopen")
    def test_streaming_response_and_request_options(self, urlopen) -> None:
        events = [
            {"message": {"role": "assistant", "content": "Hello"}, "done": False},
            {"message": {"role": "assistant", "content": " there."}, "done": True},
        ]
        response = FakeResponse(b"".join(json.dumps(event).encode() + b"\n" for event in events))
        urlopen.return_value = response
        result = "".join(self.provider.stream_chat([{"role": "user", "content": "Hi"}]))
        self.assertEqual(result, "Hello there.")
        self.assertTrue(response.closed)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["options"]["num_ctx"], 4096)

    @patch("nexus.models.ollama_provider.urlopen")
    def test_rejects_malformed_stream_and_missing_done_marker(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(b"{not-json}\n")
        with self.assertRaisesRegex(ProviderError, "malformed streaming data"):
            list(self.provider.stream_chat([]))
        urlopen.return_value = FakeResponse(b'{"message":{"content":"partial"}}\n')
        with self.assertRaisesRegex(ProviderError, "before marking it complete"):
            list(self.provider.stream_chat([]))

    @patch("nexus.models.ollama_provider.urlopen", side_effect=URLError("offline"))
    def test_chat_connection_error_is_actionable(self, _urlopen) -> None:
        with self.assertRaisesRegex(ProviderError, "Could not connect to Ollama"):
            list(self.provider.stream_chat([]))


if __name__ == "__main__":
    unittest.main()
