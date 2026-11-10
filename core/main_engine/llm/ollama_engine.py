
import asyncio
import json
import shutil
import subprocess

from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..prompt_manager import PromptManager
from .search_tools.search_engine import LangchainOllamaSearchEngine

class OllamaResponseEngine:
    """Generate text responses through a local Ollama server."""

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
        lang: str = "ru",
        prompt_preset: str = "assistant",
        custom_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.prompt_manager = PromptManager(
            lang=lang,
            preset=prompt_preset,
            custom_prompt=custom_prompt,
        )
        self.search_engine = LangchainOllamaSearchEngine()

    def _pull_model(self) -> None:
        if shutil.which("ollama") is None:
            raise RuntimeError(
                "Ollama command is not available in PATH. Install Ollama or add it to PATH."
            )

        result = subprocess.run(
            ["ollama", "pull", self.model],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                f"Could not pull Ollama model '{self.model}': {details or 'unknown error'}"
            )

    async def handle(self, request: str, web_search: bool = True) -> str:
        user_content = request

        if web_search:
            eth_context = await self.search_engine.standart_search(request=request)
            user_content = (
                f"<context>\n{eth_context}\n</context>\n\n"
                f"Используя приведенный выше контекст из интернета, "
                f"ответь на вопрос: {request}"
            )

        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": self.prompt_manager.system_prompt,
                    },
                    {"role": "user", "content": user_content},
                ],
            }
        ).encode("utf-8")

        ollama_request = Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            response_data = await asyncio.to_thread(self._post, ollama_request)
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace").strip()
            if error.code == 404 and "model" in details.lower() and "not found" in details.lower():
                self._pull_model()
                try:
                    response_data = await asyncio.to_thread(self._post, ollama_request)
                except HTTPError as retry_error:
                    retry_details = retry_error.read().decode("utf-8", errors="replace").strip()
                    raise RuntimeError(
                        f"Ollama returned HTTP {retry_error.code}: {retry_details or retry_error.reason}"
                    ) from retry_error
            else:
                raise RuntimeError(
                    f"Ollama returned HTTP {error.code}: {details or error.reason}"
                ) from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError(
                f"Could not connect to Ollama at {self.base_url}. "
                "Check that Ollama is running."
            ) from error

        message = response_data.get("message")
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Ollama returned an empty or invalid chat response.")
        return text.strip()

    def _post(self, request: Request) -> dict[str, Any]:
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("Ollama returned an invalid response payload.")
        return data