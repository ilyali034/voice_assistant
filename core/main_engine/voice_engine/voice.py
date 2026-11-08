import asyncio
import json
import sounddevice as sd
from pathlib import Path
from vosk import Model, KaldiRecognizer
from kokoro_onnx import KokoroOnnx
import numpy as np 
import urllib.request
import sys

class VoiceRecognition: 
    def __init__(self, model_path: str = "./model", samplerate: int = 16000 ):
        BASE_DIR = Path(__file__).resolve().parent
        model_path = BASE_DIR / "model" / "vosk-model-small-ru-0.22"

        self.model = Model(str(model_path))
        self.samplerate = samplerate
        self.audio_queue = asyncio.Queue()
        self.loop = None

    def _audio_callback(self, indata, frames, time, status):
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
                            return text_res  # Исправлено: возвращаем распознанную строку

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
    def __init__(self, model_path: str = "./model", samplerate: int = 16000):
        BASE_DIR = Path(__file__).resolve().parent
        resolved_model_path = BASE_DIR / "model" / "vosk-model-small-ru-0.22"

        self.model = Model(str(resolved_model_path))
        self.samplerate = samplerate
        self.audio_queue = asyncio.Queue()
        self.loop = None 

    def _audio_callback(self, indata, frames, time, status):
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
                return False 


class VoiceTTSModule: 
    def __init__(self, model_filename: str = "kokoro-v1.0.onnx", voices_filename: str = "voices-v1.0.bin"):
        BASE_DIR = Path(__file__).resolve().parent
        self.model_dir = BASE_DIR / "model"
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.model_path = self.model_dir / model_filename
        self.voices_path = self.model_dir / voices_filename

        self.urls = {
            self.model_path: "https://huggingface.co",
            self.voices_path: "https://github.com"
        }

        self._ensure_models_exist()

        self.onnx = KokoroOnnx(str(self.model_path), str(self.voices_path)) 
        self.sample_rate = 24000 

    def _progress_callback(self, block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            percent = min(int(downloaded * 100 / total_size), 100)
            sys.stdout.write(f"\rЗагрузка: [{'*' * (percent // 2)}{' ' * (50 - percent // 2)}] {percent}%")
            sys.stdout.flush()

    def _ensure_models_exist(self):
        for file_path, url in self.urls.items():
            if not file_path.exists():
                print(f"\nФайл {file_path.name} не найден. Начинаю скачивание...")
                try:
                    urllib.request.urlretrieve(url, file_path, self._progress_callback)
                    print(f"\nФайл {file_path.name} успешно загружен!")
                except Exception as e:
                    if file_path.exists():
                        file_path.unlink()
                    print(f"\nОшибка при скачивании {file_path.name}: {e}")
                    raise e

    async def say(self, text: str, voice: str = "ru_alex") -> None: 
        if not text or not text.strip():
            return 

        audio_queue = asyncio.Queue() 

        def audio_callback(outdata, frames, time, status): 
            if status: 
                print(f"Audio status: {status}") 
            try: 
                data = audio_queue.get_nowait() 
                if len(data) < len(outdata):
                    outdata[:len(data)] = data
                    outdata[len(data):].fill(0)
                    raise sd.CallbackStop
                else:
                    outdata[:] = data[:len(outdata)]
            except asyncio.QueueEmpty:
                outdata.fill(0)  

        async_gen = self.onnx.create_stream(text, voice=voice, speed=1.0, lang="z") 

        stream = sd.OutputStream(
            samplerate=self.sample_rate, 
            channels=1, 
            dtype='float32', 
            callback=audio_callback
        )

        with stream:
            try:
                async for samples, _ in async_gen:
                    samples_data = np.array(samples, dtype=np.float32).reshape(-1, 1)
                    await audio_queue.put(samples_data)
                    
                while not audio_queue.empty():
                    await asyncio.sleep(0.05)
                    
            except Exception as e:
                print(f"\nОшибка при генерации/воспроизведении речи: {e}")
