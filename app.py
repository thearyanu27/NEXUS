"""Command-line entry point for the first NEXUS local brain."""

from __future__ import annotations

import argparse
import logging
import sys

from nexus import __version__
from nexus.agent import Conversation, ConversationError
from nexus.config import ConfigurationError, Settings
from nexus.logging_config import configure_logging
from nexus.models import OllamaProvider, ProviderError

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NEXUS local AI brain (Ollama)")
    parser.add_argument("--check", action="store_true", help="check Ollama and the configured model, then exit")
    parser.add_argument("--verbose", action="store_true", help="show technical diagnostics without conversation text")
    parser.add_argument("--version", action="version", version=f"NEXUS {__version__}")
    return parser


def _run_check(provider: OllamaProvider) -> int:
    status = provider.health_check()
    print(status.message)
    if status.connected and status.models:
        print("Installed models: " + ", ".join(status.models))
    elif not status.connected:
        print("Start Ollama, then run `python app.py --check` again.")
    elif not status.model_available:
        print("Set NEXUS_MODEL to one of the installed model names, or install a model with Ollama.")
    return 0 if status.connected and status.model_available else 1


def _chat(provider: OllamaProvider, settings: Settings) -> int:
    status = provider.health_check()
    if not status.connected or not status.model_available:
        print(status.message, file=sys.stderr)
        if status.connected and status.models:
            print("Installed models: " + ", ".join(status.models), file=sys.stderr)
        print("Use `python app.py --check` for setup diagnostics.", file=sys.stderr)
        return 1

    conversation = Conversation(provider, settings)
    print(f"NEXUS is ready using local model {settings.model}. Type /help for commands.")
    while True:
        try:
            prompt = input("\nYou: ").strip()
        except EOFError:
            print("\nNEXUS session closed.")
            return 0
        if not prompt:
            continue
        command = prompt.casefold()
        if command in {"/exit", "/quit"}:
            print("NEXUS session closed.")
            return 0
        if command == "/help":
            print("Commands: /help, /clear, /exit")
            continue
        if command == "/clear":
            conversation.clear()
            print("Recent conversation cleared.")
            continue
        print("NEXUS: ", end="", flush=True)
        try:
            for chunk in conversation.stream_reply(prompt):
                print(chunk, end="", flush=True)
            print()
        except (ConversationError, ProviderError) as exc:
            logger.warning("Conversation request failed: %s", exc)
            print(f"\nNEXUS could not complete that response: {exc}")
    

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging(args.verbose)
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    provider = OllamaProvider(settings)
    if args.check:
        return _run_check(provider)
    try:
        return _chat(provider, settings)
    except KeyboardInterrupt:
        print("\nNEXUS stopped. The incomplete turn was not saved.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
