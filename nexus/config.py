"""Validated configuration for the local NEXUS brain."""

from __future__ import annotations

import os
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when a NEXUS setting is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:7b"
    timeout_seconds: float = 120.0
    num_ctx: int = 4096
    num_predict: int = 512
    temperature: float = 0.2
    max_history_messages: int = 12
    max_message_chars: int = 12_000
    memory_db_path: Path = Path(__file__).resolve().parent.parent / "data" / "nexus.sqlite3"

    def __post_init__(self) -> None:
        url = self.ollama_url.strip().rstrip("/")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError("NEXUS_OLLAMA_URL must be an http(s) URL with a host.")
        if parsed.username or parsed.password:
            raise ConfigurationError("Credentials must not be embedded in NEXUS_OLLAMA_URL.")
        if parsed.query or parsed.fragment:
            raise ConfigurationError("NEXUS_OLLAMA_URL must not contain a query or fragment.")
        if not self.model.strip() or any(ch.isspace() for ch in self.model):
            raise ConfigurationError("NEXUS_MODEL must be a non-empty model name without spaces.")
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 3600:
            raise ConfigurationError("NEXUS_TIMEOUT_SECONDS must be between 0 and 3600.")
        if not 512 <= self.num_ctx <= 32768:
            raise ConfigurationError("NEXUS_NUM_CTX must be between 512 and 32768 tokens.")
        if not 1 <= self.num_predict <= 8192:
            raise ConfigurationError("NEXUS_NUM_PREDICT must be between 1 and 8192.")
        if not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ConfigurationError("NEXUS_TEMPERATURE must be between 0 and 2.")
        if not 2 <= self.max_history_messages <= 200:
            raise ConfigurationError("NEXUS_MAX_HISTORY_MESSAGES must be between 2 and 200.")
        if not 1 <= self.max_message_chars <= 200_000:
            raise ConfigurationError("NEXUS_MAX_MESSAGE_CHARS must be between 1 and 200000.")
        object.__setattr__(self, "ollama_url", url)
        object.__setattr__(self, "model", self.model.strip())
        object.__setattr__(self, "memory_db_path", Path(self.memory_db_path).expanduser())

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """Read NEXUS settings from the environment without loading secret files."""
        env = os.environ if environ is None else environ
        try:
            timeout = float(env.get("NEXUS_TIMEOUT_SECONDS", "120"))
            num_ctx = int(env.get("NEXUS_NUM_CTX", "4096"))
            num_predict = int(env.get("NEXUS_NUM_PREDICT", "512"))
            temperature = float(env.get("NEXUS_TEMPERATURE", "0.2"))
            history = int(env.get("NEXUS_MAX_HISTORY_MESSAGES", "12"))
            max_chars = int(env.get("NEXUS_MAX_MESSAGE_CHARS", "12000"))
        except ValueError as exc:
            raise ConfigurationError("A numeric NEXUS environment setting has an invalid value.") from exc
        return cls(
            ollama_url=env.get("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434"),
            model=env.get("NEXUS_MODEL", "qwen2.5:7b"),
            timeout_seconds=timeout,
            num_ctx=num_ctx,
            num_predict=num_predict,
            temperature=temperature,
            max_history_messages=history,
            max_message_chars=max_chars,
            memory_db_path=Path(env.get(
                "NEXUS_MEMORY_DB", str(Path(__file__).resolve().parent.parent / "data" / "nexus.sqlite3")
            )),
        )
