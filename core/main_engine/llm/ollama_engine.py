import asyncio
import json
import re
import shutil
import subprocess

from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..prompt_manager import PromptManager
from .search_tools.search_engine import LangchainOllamaSearchEngine


class OllamaResponseEngine:
    """Generate text responses through a local Ollama server."""

    # Языки с небольшим словарём маркеров нужны для точного выбора между
    # языковыми группами без дополнительной ML-зависимости.
    _LANGUAGE_MARKERS = {
        "en": ("the ", "what", "where", "when", "why", "how", " is ", " are ", " of ", " and "),
        "de": ("der ", "die ", "das ", "und ", "wie ", "warum ", " ist ", "für "),
        "fr": ("le ", "la ", "les ", "et ", "quoi ", "comment ", "pourquoi ", "est "),
        "es": ("el ", "la ", "los ", "las ", "qué", "cómo", "por qué", "es "),
        "it": ("il ", "lo ", "la ", "gli ", "che ", "come", "perché", " è "),
        "pt": ("o ", "a ", "os ", "as ", "como", "por que", "porque", " é "),
        "pl": ("jak", "dlaczego", "gdzie", "czy", "co ", "jest ", " proszę "),
        "tr": ("nedir", "nasıl", "nerede", "neden", "bir ", "ve "),
        "ar": ("ما", "كيف", "لماذا", " أين", " هو ", " هي "),
        "zh": ("什么", "为什么", "怎么", "如何", "哪"),
        "ja": ("何", "どう", "なぜ", "です", "ます", "ください"),
        "ko": ("무엇", "왜", "어떻게", "입니다", "하세요"),
    }

    _LANGUAGE_NAMES = {
        "ru": "Russian",
        "uk": "Ukrainian",
        "be": "Belarusian",
        "en": "English",
        "de": "German",
        "fr": "French",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "pl": "Polish",
        "tr": "Turkish",
        "ar": "Arabic",
        "zh": "Chinese",
        "ja": "Japanese",
        "ko": "Korean",
    }

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
        self.lang = lang.lower().strip().split("-")[0].split("_")[0]
        self.prompt_manager = PromptManager(
            lang=self.lang,
            preset=prompt_preset,
            custom_prompt=custom_prompt,
        )
        self.search_engine = LangchainOllamaSearchEngine(lang=self.lang)

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

    def _detect_request_language(self, request: str) -> str:
        """Detect the language used for a request and choose an appropriate search locale."""
        text = request.casefold()

        if re.search(r"[іїєґ]", text):
            return "uk"
        if re.search(r"[ўі]", text):
            return "be"
        if re.search(r"[а-яё]", text):
            return "ru"
        if re.search(r"[А-ЯЁ]", request):
            return "ru"

        if re.search(r"[\u4e00-\u9fff]", request):
            return "zh"
        if re.search(r"[\u3040-\u30ff]", request):
            return "ja"
        if re.search(r"[\uac00-\ud7af]", request):
            return "ko"
        if re.search(r"[\u0600-\u06ff]", request):
            return "ar"

        padded = f" {text} "
        scores: dict[str, int] = {}
        for code, markers in self._LANGUAGE_MARKERS.items():
            score = sum(marker in padded for marker in markers)
            if score:
                scores[code] = score

        if scores:
            return max(scores, key=scores.get)
        return self.lang if re.search(r"[a-z]", text) or not text else "en"

    def _build_search_prompt(self, request: str, context: str, language: str) -> str:
        language_name = self._LANGUAGE_NAMES.get(language, language)
        if language == "ru":
            instructions = (
                "Используй только фрагменты, прямо относящиеся к вопросу пользователя. "
                "Игнорируй несвязанные данные, рекламу и общую справочную информацию. "
                "Не повторяй источники дословно, не выдумывай отсутствующие факты или даты "
                "и ответь по существу на русском языке. Если контекст противоречивый, прямо укажи это."
            )
        elif language == "uk":
            instructions = (
                "Використовуй цей контекст лише для фактів і дат. "
                "Не повторюй джерела дослівно, не вигадуйте відсутніх даних "
                "і дай стислу відповідь українською мовою."
            )
        elif language == "be":
            instructions = (
                "Выкарыстоўвай гэтыя звесткі толькі для фактаў і дат. "
                "Не паўтарай крыніцы дослівна і не выдумвай адсутныя дадзеныя. "
                "Адкажы па-беларуску."
            )
        else:
            instructions = (
                f"Use this context only for factual support and dates. "
                f"Do not copy sources verbatim, do not invent missing facts, "
                f"and answer in {language_name}."
            )

        return (
            f"{instructions}\n\n"
            f"<search_context>\n{context}\n</search_context>\n\n"
            f"User request: {request}"
        )

    async def handle(self, request: str, web_search: bool = True) -> str:
        user_content = request
        if web_search:
            request_language = self._detect_request_language(request)
            self.search_engine.lang = request_language
            eth_context = await self.search_engine.standart_search(request=request)
            print(f"[DEBUG] Длина найденного контекста: {len(eth_context)} символов")
            if eth_context:
                user_content = self._build_search_prompt(request, eth_context, request_language)
            else:
                language_name = self._LANGUAGE_NAMES.get(request_language, request_language)
                user_content = (
                    f"No verified web context was found. Answer the user's request in {language_name}. "
                    f"Do not claim that current web facts were checked.\n\n{request}"
                )

        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "options": {
                    "num_ctx": 8192,
                    "temperature": 0.3,
                },
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