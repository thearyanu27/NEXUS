from __future__ import annotations

import unittest

from nexus.config import ConfigurationError, Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_are_local_and_bounded(self) -> None:
        settings = Settings.from_env({})
        self.assertEqual(settings.ollama_url, "http://127.0.0.1:11434")
        self.assertEqual(settings.model, "qwen2.5:7b")
        self.assertEqual(settings.max_history_messages, 12)

    def test_environment_overrides(self) -> None:
        settings = Settings.from_env({"NEXUS_MODEL": "qwen2.5:7b", "NEXUS_NUM_CTX": "2048"})
        self.assertEqual(settings.model, "qwen2.5:7b")
        self.assertEqual(settings.num_ctx, 2048)

    def test_rejects_invalid_url_and_numeric_settings(self) -> None:
        with self.assertRaises(ConfigurationError):
            Settings(ollama_url="file:///tmp/ollama")
        with self.assertRaises(ConfigurationError):
            Settings(timeout_seconds=0)
        with self.assertRaises(ConfigurationError):
            Settings(temperature=3)
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"NEXUS_NUM_CTX": "many"})

    def test_refuses_credentials_in_url(self) -> None:
        with self.assertRaises(ConfigurationError):
            Settings(ollama_url="http://user:password@localhost:11434")


if __name__ == "__main__":
    unittest.main()
