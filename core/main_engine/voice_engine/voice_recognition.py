import queue
import sys
import numpy as np
import sounddevice as sd

class LocalVoiceRecognizer:
    def __init__(self, engine="whisper", model_size_or_path="base", sample_rate=16000):
        """
        Initialize the local speech recognition engine.
        
        :param engine: "whisper" (high accuracy dictation) or "vosk" (low-latency streaming)
        :param model_size_or_path: For whisper: "tiny", "base", "small"; For vosk: path to model folder
        :param sample_rate: Audio sampling rate (typically 16000)
        """
        self.engine = engine.lower()
        self.sample_rate = sample_rate
        self.model_size_or_path = model_size_or_path
        self._model = None
        self._recognizer = None
        self._audio_queue = queue.Queue()
        
        self._load_model()

    def _load_model(self):
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

    def transcribe_chunk(self, duration=5):
        """
        [Whisper Only] Records a specific chunk of time and returns the recognized text.
        Best for dictation workflows where you talk, stop, and receive punctuation-aware text.
        """
        if self.engine != "whisper":
            print("[Warning] transcribe_chunk method is optimized for the Whisper engine.")
            
        print(f" LISTENING ({duration}s)...")
        audio_data = sd.rec(
            int(duration * self.sample_rate), 
            samplerate=self.sample_rate, 
            channels=1, 
            dtype='float32'
        )
        sd.wait()
        print(" Processing audio...")
        
        segments, info = self._model.transcribe(audio_data.flatten(), beam_size=5)
        text_result = " ".join([segment.text for segment in segments]).strip()
        return text_result

    def _audio_callback(self, indata, frames, time, status):
        """Audio stream callback to buffer incoming microphone chunks into a queue."""
        if status:
            print(status, file=sys.stderr)
        self._audio_queue.put(bytes(indata))

    def start_streaming(self, callback_func):
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
