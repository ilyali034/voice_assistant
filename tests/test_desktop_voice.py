import threading
import unittest

import numpy as np

from desktop_client.voice import LocalVoiceInput


class FakeRecognizer:
    def __init__(self) -> None:
        self.audio: np.ndarray | None = None
        self.language: str | None = None

    def transcribe_audio(
        self,
        audio_data: np.ndarray,
        *,
        language: str | None = None,
        beam_size: int = 5,
    ) -> str:
        self.audio = audio_data
        self.language = language
        self.beam_size = beam_size
        return "распознанный текст"


class FakeInputStream:
    def __init__(self, *, callback, **_kwargs) -> None:
        self.callback = callback
        self.kwargs = _kwargs

    def __enter__(self) -> "FakeInputStream":
        audio = np.full((256, 1), 0.1, dtype=np.float32)
        self.callback(audio, len(audio), None, None)
        return self

    def __exit__(self, *args) -> bool:
        self.exit_args = args
        return False


class LocalVoiceInputTests(unittest.TestCase):
    def test_records_and_transcribes_speech_locally(self) -> None:
        recognizer = FakeRecognizer()
        statuses: list[str] = []

        def create_recognizer(**kwargs) -> FakeRecognizer:
            self.assertEqual(kwargs["engine"], "whisper")
            return recognizer

        voice_input = LocalVoiceInput(
            recognizer_factory=create_recognizer,
            stream_factory=FakeInputStream,
        )

        result = voice_input.transcribe_until_silence(
            threading.Event(),
            language="ru",
            silence_duration_s=0.01,
            on_status=statuses.append,
        )

        self.assertEqual(result, "распознанный текст")
        self.assertIsNotNone(recognizer.audio)
        self.assertEqual(recognizer.language, "ru")
        self.assertTrue(any("Распознаю" in status for status in statuses))

    def test_cancel_before_start_does_not_load_model(self) -> None:
        stop_event = threading.Event()
        stop_event.set()

        def unexpected_factory(**kwargs):
            raise AssertionError(f"recognizer should not be initialized: {kwargs}")

        voice_input = LocalVoiceInput(recognizer_factory=unexpected_factory)

        self.assertEqual(voice_input.transcribe_until_silence(stop_event), "")


if __name__ == "__main__":
    unittest.main()