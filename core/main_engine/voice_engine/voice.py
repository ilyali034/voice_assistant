import asyncio
import json
import sys
import threading
import time
import sounddevice as sd
from pathlib import Path
from vosk import Model, KaldiRecognizer
import pyttsx3

DEFAULT_VOSK_MODEL_PATH = (
    Path(__file__).resolve().parent / "model" / "vosk-model-small-ru-0.22"
)


def _load_vosk_model(model_path: str | Path | None) -> Model:
    resolved_path = Path(model_path) if model_path is not None else DEFAULT_VOSK_MODEL_PATH
    if not resolved_path.is_absolute():
        resolved_path = Path(__file__).resolve().parent / resolved_path
    if not resolved_path.is_dir():
        raise FileNotFoundError(f"Vosk model directory not found: {resolved_path}")
    return Model(str(resolved_path))


class VoiceRecognition:
    def __init__(self, model_path: str | Path | None = None, samplerate: int = 16000 ):
        self.model = _load_vosk_model(model_path)
        self.samplerate = samplerate
        self.audio_queue = asyncio.Queue()
        self.loop = None

    def _audio_callback(self, indata, _frames, _time, status):
        if status:
            print(f"Статус аудио: {status}")
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, bytes(indata))

    async def start_recognize(self) -> str:
        self.loop = asyncio.get_running_loop()
        rec = KaldiRecognizer(self.model, self.samplerate)
        
        print("Микрофон активирован. Говорите...")
        
        stream = sd.RawInputStream(
            samplerate=self.samplerate, 
            blocksize=4000, 
            dtype='int16', 
            channels=1, 
            callback=self._audio_callback
        )
        
        with stream:
            try:
                while True:
                    data = await self.audio_queue.get()
                    
                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result())
                        text_res = result.get('text', '').strip()
                        if text_res:
                            print(f"\nРаспознано: {text_res}")
                            return text_res

                    else:
                        partial = json.loads(rec.PartialResult())
                        if partial.get('partial'):
                            print(f"[В процессе]: {partial['partial']}", end='\r')
                            
            except asyncio.CancelledError:
                print("\nРаспознавание остановлено.")
                return ""
            except Exception as e:
                print(f"\nОшибка при распознавании: {e}")
                return ""


class WakeUpModule: 
    def __init__(
        self,
        model_path: str | Path | None = None,
        samplerate: int = 16000,
        *,
        model: Model | None = None,
    ):
        self.model = model if model is not None else _load_vosk_model(model_path)
        self.samplerate = samplerate
        self.audio_queue = asyncio.Queue()
        self.loop = None 

    def _audio_callback(self, indata, _frames, _time, status):
        if status:
            print(f"Статус аудио: {status}", flush=True)
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, bytes(indata))

    async def recognize_wake_up_word(self, word: str) -> bool: 
        self.loop = asyncio.get_running_loop()
        
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        rec = KaldiRecognizer(self.model, self.samplerate)
        
        stream = sd.RawInputStream(
            samplerate=self.samplerate,
            blocksize=4000,
            dtype="int16",
            channels=1,
            callback=self._audio_callback
        ) 

        target_word = word.lower().strip()

        with stream: 
            try: 
                while True: 
                    data = await self.audio_queue.get() 

                    if rec.AcceptWaveform(data): 
                        result = json.loads(rec.Result()) 
                        text = result.get("text", "").lower()
                        if target_word in text: 
                            return True
                            
            except asyncio.CancelledError:
                print("\nРаспознавание остановлено.")
                return False
            except Exception as e:
                print(f"\nОшибка при распознавании: {e}")
                raise


class VoiceTTSModule:
    """Speak responses through an installed OS voice and support remote interruption."""

    def __init__(self, lang: str = "ru", volume: float = 1.0) -> None:
        self.lang = lang.casefold().replace("_", "-")
        self.volume = max(0.0, min(1.0, volume))
        self._playback_lock = threading.Lock()
        self._active_stop: threading.Event | None = None

    async def say(self, text: str, voice: str | None = None) -> None:
        if not text or not text.strip():
            return

        stop_requested = threading.Event()
        playback_finished = threading.Event()
        with self._playback_lock:
            self._active_stop = stop_requested
        playback = asyncio.create_task(
            asyncio.to_thread(
                self._say_sync,
                text.strip(),
                voice,
                stop_requested,
            )
        )
        interrupt_listener = asyncio.create_task(
            asyncio.to_thread(
                self._wait_for_escape,
                stop_requested,
                playback_finished,
            )
        )
        try:
            await playback
        except asyncio.CancelledError:
            stop_requested.set()
            raise
        finally:
            playback_finished.set()
            with self._playback_lock:
                if self._active_stop is stop_requested:
                    self._active_stop = None
            await asyncio.gather(interrupt_listener, return_exceptions=True)

    def stop(self) -> None:
        """Request that the current speech playback stop as soon as possible."""
        with self._playback_lock:
            if self._active_stop is not None:
                self._active_stop.set()

    @staticmethod
    def _wait_for_escape(
        stop_requested: threading.Event,
        playback_finished: threading.Event,
    ) -> None:
        if sys.platform != "win32" or not sys.stdin.isatty():
            return

        import msvcrt

        while not playback_finished.wait(0.05):
            if msvcrt.kbhit() and msvcrt.getwch() == "\x1b":
                stop_requested.set()
                print("\nОтвет прерван.")
                return

    def _say_sync(
        self,
        text: str,
        preferred_voice: str | None,
        stop_requested: threading.Event,
    ) -> None:
        engine = pyttsx3.init()
        loop_started = False
        try:
            voices = engine.getProperty("voices") or []
            selected_voice = None

            if preferred_voice:
                preferred = preferred_voice.casefold()
                selected_voice = next(
                    (
                        item
                        for item in voices
                        if preferred in item.id.casefold()
                        or preferred in item.name.casefold()
                    ),
                    None,
                )

            language = self.lang.split("-", maxsplit=1)[0]
            if selected_voice is None:
                selected_voice = next(
                    (
                        item
                        for item in voices
                        if any(
                            str(code).casefold().replace("_", "-").startswith(language)
                            for code in getattr(item, "languages", [])
                        )
                    ),
                    None,
                )

            if selected_voice is not None:
                engine.setProperty("voice", selected_voice.id)
            engine.setProperty("volume", self.volume)
            engine.say(text)
            engine.startLoop(False)
            loop_started = True
            while engine.isBusy():
                if stop_requested.is_set():
                    engine.stop()
                    break
                engine.iterate()
                time.sleep(0.01)
        finally:
            if loop_started:
                engine.endLoop()
            engine.stop()
