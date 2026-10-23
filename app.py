"""Command-line entry point for the first NEXUS local brain."""

from __future__ import annotations

import argparse
import logging
import re
import sys

from nexus import __version__
from nexus.agent import Conversation, ConversationError
from nexus.agent.desktop_actions import handle_desktop_request
from nexus.agent.memory import ConversationMemoryError
from nexus.agent.speech import SpeechError, SpeechIO
from nexus.config import ConfigurationError, Settings
from nexus.logging_config import configure_logging
from nexus.models import OllamaProvider, ProviderError

logger = logging.getLogger(__name__)
_WAKE_PREFIX = re.compile(r"^\s*(?:hey|hi|okay|ok)[, ]+nexus\b[\s,:;.!?-]*(.*)$", re.IGNORECASE | re.DOTALL)


def _remove_wake_phrase(text: str) -> tuple[bool, str]:
    """Return whether a wake phrase was spoken and any words after it."""
    match = _WAKE_PREFIX.match(text)
    return (True, match.group(1).strip()) if match else (False, text.strip())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NEXUS local AI brain (Ollama)")
    parser.add_argument("--check", action="store_true", help="check Ollama and the configured model, then exit")
    parser.add_argument("--verbose", action="store_true", help="show technical diagnostics without conversation text")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--voice",
        dest="voice",
        action="store_true",
        help="start with microphone input and spoken replies (default)",
    )
    mode.add_argument(
        "--text", dest="voice", action="store_false", help="start in typing-only mode"
    )
    parser.set_defaults(voice=True)
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


def _chat(provider: OllamaProvider, settings: Settings, voice_mode: bool = False) -> int:
    status = provider.health_check()
    if not status.connected or not status.model_available:
        print(status.message, file=sys.stderr)
        if status.connected and status.models:
            print("Installed models: " + ", ".join(status.models), file=sys.stderr)
        print("Use `python app.py --check` for setup diagnostics.", file=sys.stderr)
        return 1

    try:
        conversation = Conversation(provider, settings)
    except ConversationMemoryError as exc:
        print(f"Local chat storage error: {exc}", file=sys.stderr)
        print("Check NEXUS_MEMORY_DB or remove the database file if it is damaged.", file=sys.stderr)
        return 1
    print(f"NEXUS is ready using local model {settings.model}.")
    print(f"Restored {len(conversation.history)} recent messages.")
    speech = SpeechIO()
    if voice_mode:
        print("Voice mode is on. Speak after 'Listening...'; say 'text mode' to type instead.")
    else:
        print("Text mode is on. Type /voice to use the microphone.")
    while True:
        if voice_mode:
            try:
                prompt = speech.listen()
            except SpeechError as exc:
                print(f"Voice input unavailable: {exc}")
                voice_mode = False
                continue
            if prompt is None:
                continue
            print(f"You (heard): {prompt}")
            woke, prompt = _remove_wake_phrase(prompt)
            if woke and not prompt:
                acknowledgement = "I'm listening."
                print(f"NEXUS: {acknowledgement}")
                try:
                    speech.speak(acknowledgement)
                except SpeechError as exc:
                    print(f"Speech output unavailable: {exc}")
                    voice_mode = False
                continue
            spoken_command = prompt.casefold().strip().rstrip(".!?")
            voice_commands = {
                "exit": "/exit",
                "quit": "/exit",
                "exit nexus": "/exit",
                "quit nexus": "/exit",
                "help": "/help",
                "clear chat": "/clear",
                "text mode": "/text",
                "switch to text": "/text",
            }
            prompt = voice_commands.get(spoken_command, prompt)
        else:
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
            print("Commands: /help, /clear (clear this chat), /exit, /quit")
            print("Try: open Chrome, YouTube, File Explorer, Notepad, Calculator, Paint, Task Manager, or Settings;")
            print("take a screenshot; or ask a calculation such as 'calculate (12 + 8) / 4'.")
            print("Voice is on by default. Use /text to type or /voice to listen again.")
            continue
        if command == "/voice":
            voice_mode = True
            print("Voice mode is on. Speak after the listening prompt; say 'text mode' to switch back.")
            continue
        if command == "/text":
            voice_mode = False
            print("Text mode is on.")
            continue
        if command == "/clear":
            try:
                conversation.clear()
            except ConversationMemoryError as exc:
                print(f"Could not clear saved history: {exc}")
            else:
                print("This conversation was cleared.")
            continue
        action_reply = handle_desktop_request(prompt)
        if action_reply is not None:
            print(f"NEXUS: {action_reply}")
            if voice_mode:
                try:
                    speech.speak(action_reply)
                except SpeechError as exc:
                    print(f"Speech output unavailable: {exc}")
                    voice_mode = False
            continue
        print("NEXUS: ", end="", flush=True)
        try:
            reply_parts = []
            for chunk in conversation.stream_reply(prompt):
                reply_parts.append(chunk)
                print(chunk, end="", flush=True)
            print()
            if voice_mode:
                try:
                    speech.speak("".join(reply_parts).strip())
                except SpeechError as exc:
                    print(f"Speech output unavailable: {exc}")
                    voice_mode = False
        except (ConversationError, ConversationMemoryError, ProviderError) as exc:
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
        return _chat(provider, settings, voice_mode=args.voice)
    except KeyboardInterrupt:
        print("\nNEXUS stopped. The incomplete turn was not saved.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
