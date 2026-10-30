
import asyncio
from typing import Literal

from .response_engine import ActionEngine, OllamaResponseEngine, ResponseEngine
from .task_manager import LowLevelTaskManager
from .vecs.qdrant.qdrant_cfg import QdrantCfg
from .vecs.vqdb import VQDBManager
from .voice_engine.assi_voice import AsyncSpeechEngine
from .voice_engine.voice_recognition import LocalVoiceRecognizer


AssistantMode = Literal["llm", "actions"]


class AssistentEngine:
    """Coordinate speech input/output and dispatch requests to a chosen engine."""

    def __init__(
        self,
        vec_cfg: QdrantCfg,
        voice_recognizer_engine: str = "whisper",
        voice_assi_mode: str = "online",
        lang: str = "ru",
        volume: float = 1.0,
        assistant_mode: AssistantMode = "llm",
        llm_model: str = "llama3.2",
        ollama_url: str = "http://localhost:11434",
        ollama_timeout: float = 120.0,
        prompt_preset: str = "assistant",
        custom_prompt: str | None = None,
        llm_engine: ResponseEngine | None = None,
        action_engine: ResponseEngine | None = None,
    ) -> None:
        self.vector_db = VQDBManager(vec_cfg)
        self.assistent_voice = AsyncSpeechEngine(
            mode=voice_assi_mode,
            lang=lang,
            volume=volume,
        )
        self.voice_recognizer = LocalVoiceRecognizer(engine=voice_recognizer_engine)
        self.task_manager = LowLevelTaskManager()
        self.llm_engine = llm_engine or OllamaResponseEngine(
            model=llm_model,
            base_url=ollama_url,
            timeout=ollama_timeout,
            lang=lang,
            prompt_preset=prompt_preset,
            custom_prompt=custom_prompt,
        )
        self.response_engines: dict[str, ResponseEngine] = {
            "llm": self.llm_engine,
            "actions": action_engine or ActionEngine(),
        }
        self.select_mode(assistant_mode)
        self._started = False

    @property
    def available_prompt_presets(self) -> tuple[str, ...]:
        """Return built-in presets when the configured LLM engine is Ollama."""
        return self._get_ollama_engine().prompt_manager.available_presets

    def select_prompt_preset(self, preset: str) -> None:
        """Select a built-in LLM prompt preset and clear any custom prompt."""
        self._get_ollama_engine().prompt_manager.select_preset(preset)

    def set_custom_prompt(self, prompt: str) -> None:
        """Set the system prompt written by the user for the Ollama engine."""
        self._get_ollama_engine().prompt_manager.set_custom_prompt(prompt)

    def clear_custom_prompt(self) -> None:
        """Clear the custom prompt and restore the selected built-in preset."""
        self._get_ollama_engine().prompt_manager.clear_custom_prompt()

    def _get_ollama_engine(self) -> OllamaResponseEngine:
        if not isinstance(self.llm_engine, OllamaResponseEngine):
            raise RuntimeError(
                "Prompt settings are available only with OllamaResponseEngine."
            )
        return self.llm_engine

    def select_mode(self, mode: AssistantMode) -> None:
        """Select ``llm`` for generated answers or ``actions`` for direct commands."""
        if mode not in self.response_engines:
            raise ValueError(f"Unsupported assistant mode: {mode}")
        self.assistant_mode = mode

    async def start(self) -> None:
        """Initialize persistence and start background workers."""
        if self._started:
            return

        await self.vector_db.init_database()
        self.assistent_voice.start()
        await self.task_manager.start()
        self._started = True

    async def stop(self) -> None:
        """Stop workers and close the vector database connection."""
        if self._started:
            await self.task_manager.stop()
            await self.assistent_voice.stop()
            self._started = False
        await self.vector_db.close()

    async def send_request_for_assistent(
        self,
        request: str | None = None,
        *,
        duration: int = 5,
        speak: bool = True,
    ) -> str:
        """Get a text or microphone request, generate a reply, and optionally speak it.

        When ``request`` is omitted, audio is recorded and transcribed using the
        configured recognizer. The selected engine handles the recognized text.
        """
        if request is None:
            if duration <= 0:
                raise ValueError("duration must be greater than zero")
            request = await asyncio.to_thread(
                self.voice_recognizer.transcribe_chunk,
                duration,
            )

        request = request.strip()
        if not request:
            return ""

        response = await self.response_engines[self.assistant_mode].handle(request)
        if not isinstance(response, str):
            raise TypeError("The selected response engine must return a string")

        response = response.strip()
        if speak and response:
            await self.assistent_voice.say(response)

        return response