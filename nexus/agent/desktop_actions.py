"""Allowlisted desktop actions and a small, safe arithmetic evaluator."""

from __future__ import annotations

import ast
import math
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path


_OPENING = re.compile(r"\b(open|launch|start|show|go to|take me to)\b", re.IGNORECASE)
_SCREENSHOT = re.compile(r"\b(screenshot|screen\s*shot|ss|capture (?:my )?(?:screen|display))\b", re.IGNORECASE)
_CALC_REQUEST = re.compile(r"^(?:(?:please\s+)?(?:calculate|compute|what is|what's|solve)\s+)?(.+?)\??$", re.IGNORECASE)
_APPS = {
    "notepad": ("notepad.exe", "Notepad"),
    "calculator": ("calc.exe", "Calculator"),
    "calc": ("calc.exe", "Calculator"),
    "paint": ("mspaint.exe", "Paint"),
    "task manager": ("taskmgr.exe", "Task Manager"),
}
_BINARY_OPERATORS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}
_UNARY_OPERATORS = {ast.UAdd: lambda value: value, ast.USub: lambda value: -value}


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


def _calculate(prompt: str) -> str | None:
    """Evaluate a basic arithmetic request without eval or arbitrary Python."""
    match = _CALC_REQUEST.fullmatch(prompt.strip().rstrip(".!"))
    if not match:
        return None
    expression = match.group(1).casefold()
    for spoken, symbol in (("multiplied by", "*"), ("divided by", "/"), ("times", "*"), ("plus", "+"), ("minus", "-"), ("over", "/")):
        expression = re.sub(rf"\b{spoken}\b", symbol, expression)
    expression = expression.replace("^", "**")
    if not re.fullmatch(r"[\d\s.+*/()%\-]+", expression):
        return None
    try:
        tree = ast.parse(expression, mode="eval")

        def visit(node: ast.AST) -> float:
            if isinstance(node, ast.Expression):
                return visit(node.body)
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                value = float(node.value)
            elif isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
                value = _UNARY_OPERATORS[type(node.op)](visit(node.operand))
            elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
                left, right = visit(node.left), visit(node.right)
                if isinstance(node.op, ast.Pow) and abs(right) > 100:
                    raise ValueError
                value = _BINARY_OPERATORS[type(node.op)](left, right)
            else:
                raise ValueError
            if not math.isfinite(value) or abs(value) > 1e100:
                raise ValueError
            return value

        result = visit(tree)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return "I couldn't calculate that expression. Try something like: calculate (12 + 8) / 4."
    rendered = str(int(result)) if result.is_integer() else f"{result:.12g}"
    return f"The answer is {rendered}."


_SCREENSHOT_SCRIPT = r"""$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $folder = Join-Path ([Environment]::GetFolderPath('MyPictures')) 'NEXUS Screenshots'
    [void](New-Item -ItemType Directory -Force -Path $folder)
    $file = Join-Path $folder ('Screenshot-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.png')
    $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $bitmap = [System.Drawing.Bitmap]::new($bounds.Width, $bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $bitmap.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
    [Console]::Out.WriteLine($file)
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
"""


def _take_screenshot() -> str:
    if sys.platform != "win32":
        return "Taking a screenshot is currently supported on Windows only."
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        return "I couldn't find Windows PowerShell to capture the screen."
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", _SCREENSHOT_SCRIPT],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"I couldn't capture the screen: {exc}"
    if result.returncode:
        detail = result.stderr.strip() or "Windows could not capture the screen."
        return f"I couldn't capture the screen: {detail}"
    return f"Screenshot saved to {result.stdout.strip()}"


def handle_desktop_request(prompt: str) -> str | None:
    """Run a supported desktop action, calculation, or return None for chat."""
    text = prompt.casefold().strip()

    if _SCREENSHOT.search(text) and (re.search(r"\b(take|capture|do|make)\b", text) or text in {"screenshot", "screen shot", "ss"}):
        return _take_screenshot()

    calculation = _calculate(text)
    if calculation is not None:
        return calculation

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

    for name, (executable, display_name) in _APPS.items():
        if re.search(rf"\b{re.escape(name)}\b", text):
            if os.name != "nt":
                return f"{display_name} is available only on Windows."
            try:
                subprocess.Popen([executable], close_fds=True)
            except OSError as exc:
                return f"I couldn't open {display_name}: {exc}"
            return f"Opening {display_name}."

    if re.search(r"\b(settings|windows settings)\b", text):
        if os.name != "nt":
            return "Windows Settings is available only on Windows."
        try:
            os.startfile("ms-settings:")
        except OSError as exc:
            return f"I couldn't open Windows Settings: {exc}"
        return "Opening Windows Settings."

    return None
