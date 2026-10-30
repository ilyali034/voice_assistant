import asyncio
import json
import re
import webbrowser
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
from .prompt_manager import PromptManager


class ResponseEngine(Protocol):
    async def handle(self, request: str) -> str:
        """Handle a user request and return a user-facing result."""


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

    async def handle(self, request: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": self.prompt_manager.system_prompt,
                    },
                    {"role": "user", "content": request},
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


ActionHandler = Callable[[re.Match[str]], Awaitable[str]]


class ActionEngine:
    """Execute explicitly matched desktop/web actions without an LLM."""

    def __init__(self) -> None:
        self._routes: list[tuple[re.Pattern[str], ActionHandler]] = []
        self.register_action(
            (
                r"(?:открой|запусти)(?:\s+мне)?\s+браузер",
                r"(?:open|launch)(?:\s+the)?\s+browser",
            ),
            self._open_browser,
        )
        self.register_action(
            (
                r"(?:загугли|гугли|найди\s+в\s+интернете|поищи\s+в\s+интернете)\s+(?P<query>.+)",
                r"(?:google|search\s+(?:the\s+)?web\s+for)\s+(?P<query>.+)",
            ),
            self._google_search,
        )
        self.register_action(
            (
                r"(?:открой|перейди\s+на)\s+(?:сайт\s+)?(?P<target>.+)",
                r"(?:open|go\s+to)\s+(?:the\s+)?(?:website\s+)?(?P<target>.+)",
            ),
            self._open_website,
        )

    def register_action(
        self,
        patterns: tuple[str, ...],
        handler: ActionHandler,
    ) -> None:
        """Register additional command patterns and their async action handler."""
        self._routes.extend(
            (re.compile(pattern, re.IGNORECASE), handler) for pattern in patterns
        )

    async def handle(self, request: str) -> str:
        command = request.strip()
        for pattern, handler in self._routes:
            match = pattern.fullmatch(command)
            if match:
                return await handler(match)
        return (
            "Команда не распознана. Можно попросить открыть браузер, "
            "открыть сайт или выполнить поиск в Google."
        )

    async def _open_browser(self, _: re.Match[str]) -> str:
        return await self._open_url("https://www.google.com", "Браузер открыт.")

    async def _google_search(self, match: re.Match[str]) -> str:
        query = match.group("query").strip()
        if not query:
            return "Укажите, что нужно найти."
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return await self._open_url(url, f"Ищу в Google: {query}")

    async def _open_website(self, match: re.Match[str]) -> str:
        target = match.group("target").strip()
        if not target:
            return "Укажите адрес сайта."
        if "://" not in target:
            target = f"https://{target}"

        parsed_url = urlparse(target)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            return "Можно открывать только адреса сайтов с http или https."
        return await self._open_url(target, f"Открываю сайт: {target}")

    async def _open_url(self, url: str, success_message: str) -> str:
        opened = await asyncio.to_thread(webbrowser.open_new_tab, url)
        if not opened:
            return "Не удалось открыть браузер. Проверьте настройки браузера в системе."
        return success_message
