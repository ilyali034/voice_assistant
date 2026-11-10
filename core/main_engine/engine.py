
import asyncio
import shutil
import subprocess
import time
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import Request, urlopen

from .assistant_service import AssistantService
from .response_engine import ActionEngine, ResponseEngine
from .llm.ollama_engine import OllamaResponseEngine
from .database.db_sql import DBManager
from .voice_engine.voice import VoiceRecognition, VoiceTTSModule, WakeUpModule

AssistantMode = Literal["hybrid", "llm", "actions"]


class HybridResponseEngine:
    """Route known desktop commands to actions and other requests to the LLM."""

    def __init__(self, llm: ResponseEngine, actions: ActionEngine) -> None:
        self.llm = llm
        self.actions = actions

    async def handle(self, request: str) -> str:
        if self.actions.can_handle(request):
            return await self.actions.handle(request)
        return await self.llm.handle(request)


class AssistentEngine:
    """Coordinate speech input/output and dispatch requests to a chosen engine."""

    def __init__(
        self,
        lang: str = "ru",
        volume: float = 1.0,
        assistant_mode: AssistantMode = "hybrid",
        llm_model: str = "llama3.2",
        ollama_url: str = "http://localhost:11434",
        ollama_timeout: float = 120.0,
        prompt_preset: str = "assistant",
        custom_prompt: str | None = None,
        llm_engine: ResponseEngine | None = None,
        action_engine: ActionEngine | None = None,
    ) -> None:
        self.db = DBManager(Path(__file__).resolve().parents[1] / "chat.db")
        print("Загружаю модель распознавания речи Vosk...", flush=True)
        self.voice_r = VoiceRecognition()
        self.voice_tts = VoiceTTSModule(lang=lang, volume=volume)
        self.wake_up = WakeUpModule(model=self.voice_r.model)
        self.llm_engine = llm_engine or OllamaResponseEngine(
            model=llm_model,
            base_url=ollama_url,
            timeout=ollama_timeout,
            lang=lang,
            prompt_preset=prompt_preset,
            custom_prompt=custom_prompt,
        )
        self.action_engine = action_engine or ActionEngine()
        self.hybrid_engine = HybridResponseEngine(self.llm_engine, self.action_engine)
        self.response_engines: dict[str, ResponseEngine] = {
            "llm": self.llm_engine,
            "actions": self.action_engine,
            "hybrid": self.hybrid_engine,
        }
        self.service = AssistantService(self.response_engines)
        self._ollama_server_process: subprocess.Popen[str] | None = None
        self._started = False
        self.select_mode(assistant_mode)

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
        """Select hybrid routing, LLM-only, or actions-only mode."""
        self.service.select_mode(mode)
        if not self._started:
            return
        if mode in {"hybrid", "llm"}:
            self._ensure_ollama_server_running()
        else:
            self._stop_ollama_server()

    def _should_manage_ollama(self, mode: str | None = None) -> bool:
        selected_mode = mode or self.service.assistant_mode
        if selected_mode not in {"hybrid", "llm"}:
            return False
        if not isinstance(self.llm_engine, OllamaResponseEngine):
            return False
        parsed_url = self.llm_engine.base_url.lower()
        return "localhost" in parsed_url or "127.0.0.1" in parsed_url or "0.0.0.0" in parsed_url

    def _wait_for_ollama_server(self, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        request = Request(f"{self.llm_engine.base_url}/api/tags", method="GET")

        while time.monotonic() < deadline:
            if self._ollama_server_process is not None and self._ollama_server_process.poll() is not None:
                raise RuntimeError("The Ollama server process exited before it became ready.")
            try:
                with urlopen(request, timeout=1) as response:
                    if response.status == 200:
                        return
            except (URLError, OSError, ValueError):
                pass
            time.sleep(0.5)

        raise RuntimeError(
            f"Ollama did not start on {self.llm_engine.base_url} within {timeout} seconds."
        )

    def _ensure_ollama_model_ready(self) -> None:
        if not self._should_manage_ollama():
            return

        model_name = getattr(self.llm_engine, "model", "")
        if not model_name:
            return

        if shutil.which("ollama") is None:
            raise RuntimeError(
                "Ollama command is not available in PATH. Install Ollama or add it to PATH."
            )

        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:  # pragma: no cover - Windows-specific process error
            raise RuntimeError("Could not query the installed Ollama models.") from exc

        installed = set()
        if result.returncode == 0:
            for line in (result.stdout or "").splitlines()[1:]:
                parts = line.split()
                if not parts:
                    continue
                model = parts[0].strip()
                if model:
                    installed.add(model)

        normalized = {name for name in installed if name}
        if any(model_name == name or name.startswith(f"{model_name}:") for name in normalized):
            return

        print(f"Скачиваю модель Ollama «{model_name}»...", flush=True)
        pull = subprocess.run(["ollama", "pull", model_name], check=False)
        if pull.returncode != 0:
            raise RuntimeError(
                f"Ollama could not pull model '{model_name}'. See the Ollama output above."
            )

    def _ensure_ollama_server_running(self) -> None:
        if not self._should_manage_ollama():
            return
        if self._ollama_server_process is not None and self._ollama_server_process.poll() is None:
            return

        if shutil.which("ollama") is None:
            raise RuntimeError(
                "Ollama command is not available in PATH. Install Ollama or add it to PATH."
            )

        self._ollama_server_process = subprocess.Popen(
            ["ollama", "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        self._wait_for_ollama_server()
        self._ensure_ollama_model_ready()

    def _stop_ollama_server(self) -> None:
        if self._ollama_server_process is None:
            return
        process = self._ollama_server_process
        self._ollama_server_process = None

        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=10)
            except (subprocess.TimeoutExpired, OSError):
                process.kill()

    async def start(self) -> None:
        """Initialize local persistence before accepting assistant requests."""
        if self._started:
            return
        print("Подключаю локальную базу данных...", flush=True)
        try:
            await self.db.connect()
            await self.db.init_database()
        except Exception:
            await self.db.disconnect()
            raise
        self._started = True

        if self._should_manage_ollama():
            print("Запускаю Ollama и проверяю модель...", flush=True)
            await asyncio.to_thread(self._ensure_ollama_server_running)

    async def stop(self) -> None:
        """Close local persistence resources."""
        if self._started:
            await self.db.disconnect()
            self._started = False
        self._stop_ollama_server()

    async def start_assistent(self, wake_word: str = "ассистент") -> None:
        if not self._started:
            await self.start()

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
                await self.db.save_chat_message(text=request, role="user")
                await self.db.save_chat_message(text=response, role="assistant")

        except asyncio.CancelledError:
            raise