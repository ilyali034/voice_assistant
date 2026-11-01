import queue
import sys
from typing import Any

import numpy as np
import sounddevice as sd


class LocalVoiceRecognizer:
    def __init__(
        self,
        engine: str = "whisper",
        model_size_or_path: str = "base",
        sample_rate: int = 16000,
    ) -> None:
        """
        Initialize the local speech recognition engine.
        
        :param engine: "whisper" (high accuracy dictation) or "vosk" (low-latency streaming)
        :param model_size_or_path: For whisper: "tiny", "base", "small"; For vosk: path to model folder
        :param sample_rate: Audio sampling rate (typically 16000)
        """
        self.engine = engine.lower()
        self.sample_rate = sample_rate
        self.model_size_or_path = model_size_or_path
        self._model: Any | None = None
        self._recognizer: Any | None = None
        self.last_detected_language: str | None = None
        self._audio_queue: queue.Queue[bytes] = queue.Queue()
        
        self._load_model()

    def _load_model(self) -> None:
        """Internal method for lazy-loading engines and models."""
        if self.engine == "whisper":
            from faster_whisper import WhisperModel
            print(f"[Info] Loading Whisper model ({self.model_size_or_path})...")
            self._model = WhisperModel(self.model_size_or_path, device="cpu", compute_type="int8")
            print("[Info] Whisper model loaded successfully.")
            
        elif self.engine == "vosk":
            from vosk import Model, KaldiRecognizer
            print(f"[Info] Loading Vosk model from '{self.model_size_or_path}'...")
            try:
                vosk_model = Model(self.model_size_or_path)
                self._recognizer = KaldiRecognizer(vosk_model, self.sample_rate)
                print("[Info] Vosk model loaded successfully.")
            except Exception as e:
                print(f"[Error] Failed to load Vosk: {e}")
                print("[Error] Ensure you downloaded a model from ://alphacephei.com and verified the path.")
                sys.exit(1)
        else:
            raise ValueError("Supported engines are 'whisper' or 'vosk' only.")

    def transcribe_chunk(self, duration: int) -> str:
        """
        [Whisper Only] Records a specific chunk of time and returns the recognized text.
        Best for dictation workflows where you talk, stop, and receive punctuation-aware text.
        """
        if self.engine != "whisper" or self._model is None:
            raise RuntimeError("transcribe_chunk requires a loaded Whisper model")

        print(f" LISTENING ({duration}s)...")
        audio_data = sd.rec(
            int(duration * self.sample_rate), 
            samplerate=self.sample_rate, 
            channels=1, 
            dtype='float32'
        )
        sd.wait()
        print(" Processing audio...")

        return self.transcribe_audio(audio_data.flatten())

    def transcribe_audio(
        self,
        audio_data: np.ndarray,
        *,
        language: str | None = None,
        beam_size: int = 5,
    ) -> str:
        """Transcribe a prepared mono float audio buffer with the loaded Whisper model."""
        if self.engine != "whisper" or self._model is None:
            raise RuntimeError("transcribe_audio requires a loaded Whisper model")

        options: dict[str, Any] = {"beam_size": beam_size}
        if language:
            options["language"] = language
        segments, info = self._model.transcribe(audio_data, **options)
        self.last_detected_language = info.language
        return " ".join(segment.text for segment in segments).strip()

    def _audio_callback(self, indata, frames: int, callback_time: Any, status: Any) -> None:
        """Audio stream callback to buffer incoming microphone chunks into a queue."""
        if frames <= 0:
            return
        if status:
            print(f"{status} at {callback_time.currentTime}", file=sys.stderr)
        self._audio_queue.put(bytes(indata))

    def start_streaming(self, callback_func) -> None:
        """
        [Vosk Only] Starts an infinite microphone stream.
        Passes live partial and final text strings to your custom `callback_func`.
        """
        if self.engine != "vosk":
            raise RuntimeError("Real-time streaming is only supported when using the Vosk engine.")

        print("\n Microphone active. Start speaking... (Press Ctrl+C to stop)")
        
        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate, 
                blocksize=8000, 
                dtype="int16", 
                channels=1, 
                callback=self._audio_callback
            ):
                while True:
                    data = self._audio_queue.get()
                    if self._recognizer.AcceptWaveform(data):
                        callback_func(self._recognizer.Result(), is_final=True)
                    else:
                        callback_func(self._recognizer.PartialResult(), is_final=False)
                        
        except KeyboardInterrupt:
            print("\n Streaming stream stopped.")
