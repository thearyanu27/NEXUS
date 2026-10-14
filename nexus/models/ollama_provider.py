"""Ollama's local HTTP API, implemented with Python's standard library."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nexus.config import Settings

logger = logging.getLogger(__name__)

NEXUS_SYSTEM_PROMPT = (
    "You are NEXUS, the user's local AI assistant. Speak in first person as NEXUS, "
    "be clear and helpful, and do not claim to be a human or the fictional JARVIS. "
    "If asked what model powers you, answer transparently: this NEXUS installation "
    "uses the configured Ollama model. Do not introduce yourself as the model vendor's assistant."
)


class ProviderError(RuntimeError):
    """A safe-to-display local model or transport error."""


@dataclass(frozen=True, slots=True)
class HealthStatus:
    connected: bool
    model_available: bool
    models: tuple[str, ...]
    message: str


class OllamaProvider:
    """Minimal Ollama provider with health checks and streaming chat."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_metrics: dict[str, int | float] | None = None

    @property
    def tags_url(self) -> str:
        return f"{self.settings.ollama_url}/api/tags"

    @property
    def chat_url(self) -> str:
        return f"{self.settings.ollama_url}/api/chat"

    def health_check(self) -> HealthStatus:
        """Check Ollama and whether the configured model is present."""
        request = Request(self.tags_url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            logger.warning("Ollama tags endpoint returned HTTP %s.", exc.code)
            return HealthStatus(False, False, (), f"Ollama returned HTTP {exc.code} while listing models.")
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError):
                message = f"Ollama did not respond within {self.settings.timeout_seconds:g} seconds."
            else:
                message = f"Could not connect to Ollama at {self.settings.ollama_url}. Is it running?"
            logger.info("Ollama health check failed (%s).", type(exc).__name__)
            return HealthStatus(False, False, (), message)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Ollama returned malformed model-list data (%s).", type(exc).__name__)
            return HealthStatus(False, False, (), "Ollama returned an invalid model list.")

        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            return HealthStatus(False, False, (), "Ollama returned an unexpected model-list response.")

        names = tuple(
            str(item.get("name") or item.get("model"))
            for item in payload["models"]
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        )
        available = self.settings.model in names
        if available:
            message = f"Ollama is ready; configured model {self.settings.model!r} is available."
        else:
            message = f"Ollama is running, but configured model {self.settings.model!r} is not installed."
        return HealthStatus(True, available, names, message)

    def stream_chat(self, messages: Iterable[Mapping[str, str]]) -> Iterator[str]:
        """Stream response text; closing the iterator closes the HTTP response."""
        self.last_metrics = None
        safe_messages: list[dict[str, str]] = []
        for message in messages:
            role, content = message.get("role"), message.get("content")
            if role not in {"system", "user", "assistant"} or not isinstance(content, str):
                raise ProviderError("Chat history contains an invalid message.")
            safe_messages.append({"role": role, "content": content})
        safe_messages.insert(0, {
            "role": "system",
            "content": f"{NEXUS_SYSTEM_PROMPT} The configured model is {self.settings.model}.",
        })

        body = json.dumps(
            {
                "model": self.settings.model,
                "messages": safe_messages,
                "stream": True,
                "options": {
                    "num_ctx": self.settings.num_ctx,
                    "num_predict": self.settings.num_predict,
                    "temperature": self.settings.temperature,
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            self.chat_url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
            method="POST",
        )
        try:
            response = urlopen(request, timeout=self.settings.timeout_seconds)
        except HTTPError as exc:
            logger.warning("Ollama chat endpoint returned HTTP %s.", exc.code)
            if exc.code == 404:
                raise ProviderError("Ollama could not find the model or chat endpoint. Check the model name and Ollama version.") from None
            raise ProviderError(f"Ollama returned HTTP {exc.code} while starting the chat.") from None
        except (URLError, TimeoutError, OSError) as exc:
            logger.info("Ollama chat connection failed (%s).", type(exc).__name__)
            if isinstance(exc, TimeoutError):
                raise ProviderError(f"Ollama did not respond within {self.settings.timeout_seconds:g} seconds.") from None
            raise ProviderError(f"Could not connect to Ollama at {self.settings.ollama_url}. Is it running?") from None

        completed = False
        try:
            for line_number, raw_line in enumerate(response, start=1):
                if not raw_line.strip():
                    continue
                try:
                    event: Any = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ProviderError(f"Ollama sent malformed streaming data at line {line_number}.") from exc
                if not isinstance(event, dict):
                    raise ProviderError(f"Ollama sent an invalid streaming event at line {line_number}.")
                if event.get("error"):
                    raise ProviderError("Ollama reported a model error while generating the response.")
                message = event.get("message", {})
                if not isinstance(message, dict):
                    raise ProviderError(f"Ollama sent an invalid message at line {line_number}.")
                content = message.get("content", "")
                if content is not None and not isinstance(content, str):
                    raise ProviderError(f"Ollama sent invalid response text at line {line_number}.")
                if content:
                    yield content
                if event.get("done") is True:
                    metric_keys = ("total_duration", "load_duration", "prompt_eval_count", "eval_count", "eval_duration")
                    self.last_metrics = {
                        key: value
                        for key in metric_keys
                        if isinstance((value := event.get(key)), (int, float)) and not isinstance(value, bool)
                    }
                    completed = True
                    break
            if not completed:
                raise ProviderError("Ollama ended the response before marking it complete.")
        except (TimeoutError, OSError) as exc:
            logger.info("Ollama stream was interrupted (%s).", type(exc).__name__)
            raise ProviderError("The Ollama response stream was interrupted.") from None
        finally:
            response.close()
