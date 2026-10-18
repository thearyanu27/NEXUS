"""Optional Windows-native speech input and output for NEXUS."""

from __future__ import annotations

import math
import os
import tempfile
import time
import wave
from collections import deque
from pathlib import Path


class SpeechError(RuntimeError):
    """Raised when local speech input or voice output is unavailable."""


class SpeechIO:
    """Use local Whisper transcription and Piper voice output."""

    def __init__(self) -> None:
        self._voice = None
        self._recognizer = None

    def _load_recognizer(self):
        if self._recognizer is not None:
            return self._recognizer
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SpeechError("Local Whisper speech support is missing. Install it with `python -m pip install -e .`.") from exc
        model_name = os.environ.get("NEXUS_WHISPER_MODEL", "small").strip() or "small"
        device = os.environ.get("NEXUS_WHISPER_DEVICE", "cpu").strip().casefold()
        compute_type = os.environ.get("NEXUS_WHISPER_COMPUTE_TYPE", "float16" if device == "cuda" else "int8")
        self._language = os.environ.get("NEXUS_WHISPER_LANGUAGE", "en").strip().casefold() or "en"
        try:
            self._recognizer = WhisperModel(model_name, device=device, compute_type=compute_type)
        except Exception as exc:
            raise SpeechError(
                f"Could not load local Whisper model {model_name!r} ({device}/{compute_type}): {exc}. "
                "The model downloads once on first use; check the Whisper settings if it cannot start."
            ) from exc
        return self._recognizer

    @staticmethod
    def _record_phrase() -> Path | None:
        """Record one phrase with speech-triggered start and a longer pause to finish."""
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise SpeechError("Microphone capture support is missing. Install it with `python -m pip install -e .`.") from exc

        sample_rate = 16_000
        block_size = 480  # 30 ms blocks, suitable for voice activity checks.
        silence_to_finish = 1.25
        max_phrase_seconds = 20
        max_wait_seconds = 10
        noise_floor = 100.0
        threshold = 260.0
        chunks: list[bytes] = []
        pre_roll: deque[bytes] = deque(maxlen=7)
        recording = False
        last_voice = 0.0
        started_at = time.monotonic()
        try:
            with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16", blocksize=block_size) as stream:
                while True:
                    data, overflowed = stream.read(block_size)
                    if overflowed:
                        continue
                    samples = data.reshape(-1)
                    level = math.sqrt(sum(int(sample) * int(sample) for sample in samples) / len(samples))
                    now = time.monotonic()
                    if not recording:
                        if level > max(threshold, noise_floor * 2.2):
                            recording = True
                            chunks.extend(pre_roll)
                            chunks.append(data.tobytes())
                            last_voice = now
                            print("I heard you; keep speaking, then pause to send.")
                        else:
                            noise_floor = noise_floor * 0.94 + level * 0.06
                            if now - started_at >= max_wait_seconds:
                                return None
                            pre_roll.append(data.tobytes())
                        continue

                    chunks.append(data.tobytes())
                    if level > max(threshold * 0.5, noise_floor * 1.8):
                        last_voice = now
                    if now - last_voice >= silence_to_finish or now - started_at >= max_phrase_seconds:
                        break
        except Exception as exc:
            raise SpeechError(f"Could not record from the default microphone: {exc}") from exc

        with tempfile.NamedTemporaryFile(prefix="nexus-mic-", suffix=".wav", delete=False) as audio_file:
            path = Path(audio_file.name)
        try:
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(sample_rate)
                output.writeframes(b"".join(chunks))
        except OSError as exc:
            path.unlink(missing_ok=True)
            raise SpeechError(f"Could not prepare microphone audio for transcription: {exc}") from exc
        return path

    def listen(self) -> str | None:
        """Listen through the default microphone and transcribe locally with Whisper."""
        if self._recognizer is None:
            print("Loading local speech recognition (first use downloads the model once)...")
            self._load_recognizer()
        print("Listening... start speaking when ready.")
        audio_path = self._record_phrase()
        if audio_path is None:
            print("I didn't hear speech. Check your microphone and try again.")
            return None
        model = self._recognizer
        try:
            segments, _info = model.transcribe(
                str(audio_path),
                language=None if self._language == "auto" else self._language,
                beam_size=5,
                condition_on_previous_text=False,
                initial_prompt="NEXUS, Chrome, YouTube, File Explorer, screenshot, calculator, Notepad, Paint, Task Manager.",
            )
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
        except SpeechError:
            raise
        except Exception as exc:
            raise SpeechError(f"Local speech recognition failed: {exc}") from exc
        finally:
            audio_path.unlink(missing_ok=True)
        if not transcript:
            print("I couldn't make out those words. Try speaking a little closer to the microphone.")
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
