"""Small, fixed set of local desktop actions for the terminal assistant."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path


_OPENING = re.compile(r"\b(open|launch|start|show|go to|take me to)\b", re.IGNORECASE)


def _find_chrome() -> str | None:
    """Find an installed Chrome executable without invoking a shell."""
    on_path = shutil.which("chrome") or shutil.which("chrome.exe")
    if on_path:
        return on_path

    roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
    for root in filter(None, roots):
        candidate = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def handle_desktop_request(prompt: str) -> str | None:
    """Run a supported desktop action, or return None for normal chat."""
    text = prompt.casefold().strip()
    if not _OPENING.search(text):
        return None

    if re.search(r"\b(file\s*explorer|explorer|folders?)\b", text):
        if os.name != "nt":
            return "File Explorer is available only on Windows."
        try:
            subprocess.Popen(["explorer.exe"], close_fds=True)
        except OSError as exc:
            return f"I couldn't open File Explorer: {exc}"
        return "Opening File Explorer."

    if re.search(r"\b(chrome|google\s+chrome)\b", text):
        chrome = _find_chrome()
        if chrome is None:
            return "I couldn't find Google Chrome on this PC."
        try:
            subprocess.Popen([chrome], close_fds=True)
        except OSError as exc:
            return f"I couldn't open Chrome: {exc}"
        return "Opening Chrome."

    if re.search(r"\b(youtube|you\s*tube|yt)\b", text):
        try:
            opened = webbrowser.open_new_tab("https://www.youtube.com")
        except webbrowser.Error as exc:
            return f"I couldn't open YouTube: {exc}"
        return "Opening YouTube." if opened else "I couldn't open YouTube in your browser."

    return None
