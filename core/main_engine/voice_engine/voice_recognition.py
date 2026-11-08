import asyncio
import json
import sounddevice as sd
from pathlib import Path
from vosk import Model, KaldiRecognizer
from core.main_engine.database.db_sql import DBManager 

class VoiceRecognition: 
    def __init__(self, vec_cfg, model_path: str = "./model", samplerate: int = 16000 ):
        BASE_DIR = Path(__file__).resolve().parent
        model_path = BASE_DIR / "models" / "vosk-model-small-ru-0.22"

        self.vect = DBManager(vec_cfg)
        self.model = Model(model_path)
        self.samplerate = samplerate
        self.audio_queue = asyncio.Queue()
        self.loop = None

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f"Статус аудио: {status}")
        
        self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, bytes(indata))

    async def start_recognize(self):
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
                        if result.get('text'):
                            print(f"\n[Финальный текст]: {result['text']}")

                    else:
                        partial = json.loads(rec.PartialResult())
                        if partial.get('partial'):
                            print(f"[В процессе]: {partial['partial']}", end='\r')
                            
            except asyncio.CancelledError:
                print("\nРаспознавание остановлено.")
            except Exception as e:
                print(f"\nОшибка при распознавании: {e}")

