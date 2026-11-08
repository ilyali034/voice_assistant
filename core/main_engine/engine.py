
import asyncio
from typing import Literal

from .assistant_service import AssistantService
from .response_engine import ActionEngine, OllamaResponseEngine, ResponseEngine
from .database.db_sql import DBManager 
from .voice_engine.voice import VoiceRecognition, VoiceTTSModule
from .voice_engine.voice import VoiceRecognition, WakeUpModule

AssistantMode = Literal["llm", "actions"]


class AssistentEngine:
    """Coordinate speech input/output and dispatch requests to a chosen engine."""

    def __init__(
        self,
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
        self.db = DBManager("./core/chat.db")
        self.voice_r = VoiceRecognition()
        self.voice_tts = VoiceTTSModule(
                model_path="models/kokoro-v1.0.onnx", 
                voices_path="models/voices-v1.0.bin")
        self.wake_up = WakeUpModule()
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
        self.service = AssistantService(self.response_engines)
        self.select_mode(assistant_mode)
        self._started = False

    @property
    def assistant_mode(self) -> str:
        """Return the selected response mode."""
        return self.service.assistant_mode

    @assistant_mode.setter
    def assistant_mode(self, mode: AssistantMode) -> None:
        self.service.select_mode(mode)

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
        self.service.select_mode(mode)

    async def start(self) -> None:
        """Initialize persistence and start background workers."""
        if self._started:
            return
        self.db.connect()
        self.db.init_database() 

    async def stop(self) -> None:
        """Stop workers and close the vector database connection."""
        if self._started:
            await self.assistent_voice.stop()
            self._started = False
        if self.vector_db is not None:
            await self.vector_db.close()

    async def start_assistent(self, wake_word: str = "ассистент") -> None:

        try:
            while True:
                detected = await self.wake_up.recognize_wake_up_word(wake_word)
                if not detected:
                    return

                request = await self.voice_r.start_recognize()
                if not request:
                    continue

                response = await self.service.handle_request(request)
                await self.voice_tts.say(response) 

                try: 
                    await self.db.save_chat_message(text=request, role="user") 
                    await self.db.save_chat_message(text=response, role="assistent") 
                except Exception: 
                    raise 

        except asyncio.CancelledError:
            raise