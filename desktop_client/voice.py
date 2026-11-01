import queue
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import numpy as np
import sounddevice as sd

from core.main_engine.voice_engine.voice_recognition import LocalVoiceRecognizer


class _AudioTranscriber(Protocol):
    def transcribe_audio(
        self,
        audio_data: np.ndarray,
        *,
        language: str | None = None,
        beam_size: int = 5,
    ) -> str: ...


RecognizerFactory = Callable[..., _AudioTranscriber]
InputStreamFactory = Callable[..., Any]


class LocalVoiceInput:
    """Record microphone input locally and stop on speech silence or user request."""

    def __init__(
        self,
        model_size: str = "base",
        sample_rate: int = 16000,
        recognizer_factory: RecognizerFactory = LocalVoiceRecognizer,
        stream_factory: InputStreamFactory = sd.InputStream,
    ) -> None:
        self.model_size = model_size
        self.sample_rate = sample_rate
        self.recognizer_factory = recognizer_factory
        self.stream_factory = stream_factory
        self._recognizer: _AudioTranscriber | None = None

    def transcribe_until_silence(
        self,
        stop_event: threading.Event,
        *,
        language: str = "ru",
        max_duration_s: float = 15.0,
        silence_duration_s: float = 0.8,
        start_silence_s: float = 3.0,
        rms_threshold: float = 0.015,
        on_status: Callable[[str], None] | None = None,
    ) -> str:
        """Listen until stopped, a silence boundary is reached, or the limit expires."""
        if stop_event.is_set():
            return ""
        if self._recognizer is None:
            if on_status is not None:
                on_status("Загружаю локальную модель распознавания…")
            self._recognizer = self.recognizer_factory(
                engine="whisper",
                model_size_or_path=self.model_size,
                sample_rate=self.sample_rate,
            )
        if stop_event.is_set():
            return ""

        audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)
        captured_blocks: list[np.ndarray] = []

        def audio_callback(indata, frames, callback_time, status) -> None:
            if frames <= 0:
                return
            if status and on_status is not None:
                on_status(f"Состояние микрофона: {status} ({callback_time.currentTime:.2f})")
            try:
                audio_queue.put_nowait(indata[:frames, 0].copy())
            except queue.Full:
                pass

        if on_status is not None:
            on_status("Слушаю… остановка по паузе или кнопке (до 15 секунд)")

        started_at = time.monotonic()
        last_voice_at: float | None = None
        speech_started = False
        with self.stream_factory(
            samplerate=self.sample_rate,
            blocksize=1024,
            channels=1,
            dtype="float32",
            callback=audio_callback,
        ):
            while not stop_event.is_set():
                now = time.monotonic()
                elapsed = now - started_at
                if elapsed >= max_duration_s:
                    break
                if speech_started and last_voice_at is not None:
                    if now - last_voice_at >= silence_duration_s:
                        break
                elif elapsed >= start_silence_s:
                    break

                try:
                    audio_block = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    if speech_started and last_voice_at is not None:
                        if now - last_voice_at >= silence_duration_s:
                            break
                    elif elapsed >= start_silence_s:
                        break
                    continue

                captured_blocks.append(audio_block)
                block_rms = float(np.sqrt(np.mean(np.square(audio_block))))
                if block_rms >= rms_threshold:
                    speech_started = True
                    last_voice_at = now

        if not speech_started or not captured_blocks:
            return ""
        if on_status is not None:
            on_status("Распознаю речь…")

        audio_data = np.concatenate(captured_blocks).astype(np.float32, copy=False)
        return self._recognizer.transcribe_audio(audio_data, language=language)