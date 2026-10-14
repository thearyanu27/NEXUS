"""Optional Windows-native speech input and output for NEXUS."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


class SpeechError(RuntimeError):
    """Raised when the Windows speech recognizer or voice is unavailable."""


_RECOGNIZE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$recognizer = $null
try {
    Add-Type -AssemblyName System.Speech
    $culture = [System.Globalization.CultureInfo]::GetCultureInfo('en-US')
    $recognizer = [System.Speech.Recognition.SpeechRecognitionEngine]::new($culture)
    $grammar = [System.Speech.Recognition.DictationGrammar]::new()
    $recognizer.LoadGrammar($grammar)
    $recognizer.SetInputToDefaultAudioDevice()
    $recognizer.InitialSilenceTimeout = [TimeSpan]::FromSeconds(8)
    $recognizer.EndSilenceTimeout = [TimeSpan]::FromSeconds(1.1)
    $recognizer.BabbleTimeout = [TimeSpan]::FromSeconds(25)
    $result = $recognizer.Recognize([TimeSpan]::FromSeconds(35))
    if ($null -ne $result) { [Console]::Out.WriteLine($result.Text) }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
    if ($null -ne $recognizer) { $recognizer.Dispose() }
}
"""


class SpeechIO:
    """Use Windows speech recognition and a local Piper neural voice."""

    def __init__(self) -> None:
        self._voice = None

    def _powershell(self) -> str:
        if sys.platform != "win32":
            raise SpeechError("NEXUS voice mode currently requires Windows speech services.")
        executable = shutil.which("powershell.exe")
        if executable is None:
            raise SpeechError("Windows PowerShell could not be found.")
        return executable

    def listen(self) -> str | None:
        """Listen once through the default microphone until Windows detects silence."""
        executable = self._powershell()
        print("Listening... speak now. Pause to send.")
        try:
            result = subprocess.run(
                [executable, "-NoProfile", "-NonInteractive", "-Command", _RECOGNIZE_SCRIPT],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=40,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SpeechError("Speech recognition timed out. Try a shorter phrase.") from exc
        except OSError as exc:
            raise SpeechError(f"Could not start Windows speech recognition: {exc}") from exc
        if result.returncode:
            detail = result.stderr.strip() or "Windows could not recognize speech."
            if "No audio" in detail or "audio input" in detail.casefold():
                detail += " Check that a default microphone is connected and enabled."
            raise SpeechError(detail)
        transcript = result.stdout.strip()
        if not transcript:
            print("I didn't hear anything.")
            return None
        return transcript

    def speak(self, text: str) -> None:
        """Speak text through the downloaded local Piper voice."""
        if not text.strip():
            return
        try:
            import winsound
            from piper import PiperVoice
        except ImportError as exc:
            raise SpeechError("Piper speech support is missing. Install NEXUS with `python -m pip install -e .`.") from exc

        model_path = Path(__file__).resolve().parents[2] / "data" / "voices" / "en_US-lessac-medium.onnx"
        if not model_path.is_file():
            raise SpeechError(
                "NEXUS's Piper voice is missing. Download it with "
                "`python -m piper.download_voices en_US-lessac-medium --data-dir data/voices`."
            )
        try:
            if self._voice is None:
                self._voice = PiperVoice.load(str(model_path))
            with tempfile.TemporaryDirectory(prefix="nexus-voice-") as temp_dir:
                audio_path = Path(temp_dir) / "reply.wav"
                with wave.open(str(audio_path), "wb") as output:
                    self._voice.synthesize_wav(text, output)
                winsound.PlaySound(str(audio_path), winsound.SND_FILENAME)
        except Exception as exc:
            raise SpeechError(f"NEXUS could not generate or play its Piper voice: {exc}") from exc
