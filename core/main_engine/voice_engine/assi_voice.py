import abc
import asyncio
import os
import sys
from typing import Optional
import edge_tts
import pyttsx3

class BaseTTSBackend(abc.ABC):
    """Abstract base class to define consistent behavior for all TTS providers."""

    @abc.abstractmethod
    async def say(self, text: str) -> None:
        """Render text and play it immediately without blocking the async event loop."""
        pass

    @abc.abstractmethod
    async def save(self, text: str, path: str) -> None:
        """Render text and export it directly to an audio file asynchronously."""
        pass

class Pyttsx3Backend(BaseTTSBackend):
    """Offline TTS backend wrapped inside an executor to prevent blocking the async loop."""

    def __init__(self, lang: str, rate: int, volume: float):
        self.lang = lang
        self.rate = rate
        self.volume = volume
        self.engine = None

    def _init_engine(self):
        if self.engine is None:
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", self.rate)
            self.engine.setProperty("volume", self.volume)
            voices = self.engine.getProperty("voices")
            for voice in voices:
                if self.lang in voice.languages or self.lang in voice.id.lower():
                    self.engine.setProperty("voice", voice.id)
                    break

    def _sync_say(self, text: str):
        self._init_engine()
        self.engine.say(text)
        self.engine.runAndWait()

    def _sync_save(self, text: str, path: str):
        self._init_engine()
        self.engine.save_to_file(text, path)
        self.engine.runAndWait()

    async def say(self, text: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_say, text)

    async def save(self, text: str, path: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_save, text, path)

class EdgeTTSBackend(BaseTTSBackend):
    """High-quality cloud TTS backend utilizing Microsoft Edge's neural voices natively."""

    def __init__(self, lang: str):
        if lang == "ru":
            self.voice = "ru-RU-DmitryNeural"
        else:
            self.voice = "en-US-ChristopherNeural"

    async def say(self, text: str) -> None:
        temp_file = "temp_playback.mp3"
        await self.save(text, temp_file)
        await self._play_file(temp_file)
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass

    async def save(self, text: str, path: str) -> None:
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(path)
        except Exception as e:
            print(f"[Edge-TTS Error]: Generation failed. Details: {e}", file=sys.stderr)

    async def _play_file(self, path: str) -> None:
        """Asynchronously triggers hidden platform-native background audio tasks."""
        if os.name == "nt":  # Windows
            proc = await asyncio.create_subprocess_shell(
                f'start /b "" "{path}"',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        elif sys.platform == "darwin":  # macOS
            proc = await asyncio.create_subprocess_exec(
                "afplay", path, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
        else:  # Linux
            proc = await asyncio.create_subprocess_exec(
                "play", path, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()


class AsyncSpeechEngine:
    """Core controller using an asyncio Queue for seamless, non-blocking background speech execution."""

    def __init__(self, mode: str = "online", lang: str = "ru", rate: int = 150, volume: float = 1.0):
        self.mode = mode.lower()
        self.lang = lang
        self.rate = rate
        self.volume = volume

        self.queue = asyncio.Queue()
        self.worker_task: Optional[asyncio.Task] = None
        self.backend = self._create_backend()

    def _create_backend(self) -> BaseTTSBackend:
        if self.mode == "online":
            return EdgeTTSBackend(self.lang)
        return Pyttsx3Backend(self.lang, self.rate, self.volume)

    async def _worker(self) -> None:
        """Asynchronous worker listening to the pipeline queue indefinitely."""
        while True:
            try:
                text, file_path = await self.queue.get()
                if file_path:
                    await self.backend.save(text, file_path)
                else:
                    await self.backend.say(text)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Engine Worker Error]: {e}", file=sys.stderr)

    def start(self) -> None:
        """Spawn the asynchronous background worker loop task."""
        if self.worker_task and not self.worker_task.done():
            return
        self.worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Gracefully close consumer pipeline workers and queues."""
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

    async def say(self, text: str, async_mode: bool = False) -> None:
        """Speak out text directly or enqueue it non-blockingly."""
        if async_mode:
            await self.queue.put((text, None))
        else:
            await self.backend.say(text)

    async def save(self, text: str, path: str, async_mode: bool = False) -> None:
        """Export text to file format directly or schedule it in background task arrays."""
        if async_mode:
            await self.queue.put((text, path))
        else:
            await self.backend.save(text, path)
