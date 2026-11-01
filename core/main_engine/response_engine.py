import asyncio
import getpass
import json
import os
import re
import shlex
import subprocess
import sys
import time
import webbrowser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

import psutil
import yaml

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


@dataclass(frozen=True)
class _ActionRoute:
    pattern: re.Pattern[str]
    handler: ActionHandler


class RequestRecognizer:
    """Normalize recognized speech and match it against precompiled actions."""

    _assistant_prefix = re.compile(
        r"^(?:(?:эй[\s,:.!?-]+)?ассистент|assistant)"
        r"(?:[\s,:.!?-]+(?:пожалуйста|please))?[\s,:.!?-]*"
        r"|^(?:пожалуйста|please|слушай)[\s,:.!?-]*",
        re.IGNORECASE,
    )
    _polite_suffix = re.compile(
        r"[\s,:.!?-]*(?:пожалуйста|плиз|please)[.!?]*$",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._routes: list[_ActionRoute] = []

    def register_action(
        self,
        patterns: tuple[str, ...],
        handler: ActionHandler,
    ) -> None:
        """Compile action patterns once when they are registered."""
        self._routes.extend(
            _ActionRoute(re.compile(pattern, re.IGNORECASE), handler)
            for pattern in patterns
        )

    @classmethod
    def normalize(cls, request: str) -> str:
        """Normalize common speech-recognition noise without changing intent."""
        command = " ".join(request.casefold().split())
        command = cls._assistant_prefix.sub("", command, count=1)
        command = cls._polite_suffix.sub("", command, count=1)
        return command.strip(" \t\r\n.,!?;:")

    def recognize(self, request: str) -> tuple[ActionHandler, re.Match[str]] | None:
        """Return the first matching handler and its captured request entities."""
        command = self.normalize(request)
        if not command:
            return None

        for route in self._routes:
            match = route.pattern.fullmatch(command)
            if match is not None:
                return route.handler, match
        return None


class ActionEngine:
    """Execute configured desktop, process, shell, and web actions."""

    _default_config_path = Path(__file__).resolve().parents[1] / "cfgs" / "assistant.yaml"
    _search_templates = {
        "google": "https://www.google.com/search?q={query}",
        "yandex": "https://yandex.com/search/?text={query}",
        "duckduckgo": "https://duckduckgo.com/?q={query}",
        "bing": "https://www.bing.com/search?q={query}",
    }

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        config_path: str | Path | None = None,
    ) -> None:
        self.config_path = Path(config_path) if config_path else self._default_config_path
        self.config = config if config is not None else self._load_config(self.config_path)
        self.shell_config = self.config.get("shell", {})
        self.apps = self._normalize_mapping(self.shell_config.get("apps", {}))
        self.processes = self._normalize_mapping(self.shell_config.get("processes", {}))
        self.web_config = self.config.get("web", {})
        self.sites = self._normalize_mapping(self.web_config.get("sites", {}))
        self.search_engine = str(self.web_config.get("search_engine", "google")).casefold()
        self.safe_commands = tuple(self.shell_config.get("safe_prefixes", ()))
        self.blocked_patterns = tuple(
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.shell_config.get("blocked_regex", ())
        )
        self.confirm_words = {
            RequestRecognizer.normalize(str(word))
            for word in self.shell_config.get("confirm_words", ("подтверждаю",))
        }
        self.cancel_words = {"отмена", "отмени", "cancel"}
        self._pending_process_close: tuple[str, float] | None = None
        self.recognizer = RequestRecognizer()
        self.register_action(
            (
                r"(?:открой|запусти|включи)(?:\s+мне)?\s+(?:веб-)?браузер",
                r"(?:open|launch)(?:\s+the)?\s+browser",
            ),
            self._open_browser,
        )
        self.register_action(
            (
                r"(?:загугли|гугли|найди|поищи)(?:\s+(?:в\s+интернете|в\s+сети|в\s+гугле))?\s*(?P<query>.*)",
                r"(?:google|search(?:\s+(?:the\s+)?web)?\s+for)\s*(?P<query>.*)",
            ),
            self._google_search,
        )
        self.register_action(
            (
                r"(?:(?:открой|посети)\s+(?:сайт|страницу)|(?:перейди|зайди)\s+на\s+(?:сайт\s+)?)\s*(?P<target>.+)",
                r"(?:open|visit)\s+(?:the\s+)?(?:website|page)\s+(?P<target>.+)",
                r"go\s+to\s+(?:the\s+)?(?:website\s+)?(?P<target>.+)",
            ),
            self._open_website,
        )
        self.register_action(
            (
                r"(?:открой|запусти|включи)(?:\s+мне)?\s+(?:приложение\s+)?(?P<target>.+)",
                r"(?:open|start|launch)(?:\s+the)?\s+(?:app\s+)?(?P<target>.+)",
            ),
            self._open_app,
        )
        self.register_action(
            (
                r"(?:закрой|останови|заверши)(?:\s+процесс)?\s+(?P<target>.+)",
                r"(?:close|stop|terminate)(?:\s+the)?\s+(?:process\s+)?(?P<target>.+)",
            ),
            self._request_process_close,
        )
        self.register_action(
            (
                r"(?:выполни|запусти)\s+команду\s+(?P<command>.+)",
                r"run\s+command\s+(?P<command>.+)",
            ),
            self._run_safe_command,
        )

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Assistant config must contain a YAML mapping: {path}")
        return data

    @staticmethod
    def _normalize_mapping(mapping: Any) -> dict[str, str]:
        if not isinstance(mapping, dict):
            return {}
        return {
            RequestRecognizer.normalize(str(alias)): str(value).strip()
            for alias, value in mapping.items()
            if str(alias).strip() and str(value).strip()
        }

    def register_action(
        self,
        patterns: tuple[str, ...],
        handler: ActionHandler,
    ) -> None:
        """Register additional command patterns and their async action handler."""
        self.recognizer.register_action(patterns, handler)

    async def handle(self, request: str) -> str:
        command = RequestRecognizer.normalize(request)
        pending = self._pending_process_close
        if pending is not None:
            target, expires_at = pending
            self._pending_process_close = None
            if time.monotonic() <= expires_at and command in self.confirm_words:
                return await self._terminate_configured_processes(target)
            if command in self.cancel_words:
                return "Закрытие процесса отменено."

        recognized = self.recognizer.recognize(request)
        if recognized is not None:
            handler, match = recognized
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
        template = self._search_templates.get(self.search_engine)
        if template is None:
            return f"Неизвестная поисковая система: {self.search_engine}."
        url = template.format(query=quote_plus(query))
        return await self._open_url(url, f"Ищу: {query}")

    async def _open_website(self, match: re.Match[str]) -> str:
        target = match.group("target").strip()
        configured_url = self.sites.get(RequestRecognizer.normalize(target))
        if configured_url:
            target = configured_url
        if not target:
            return "Укажите адрес сайта."
        if "://" not in target:
            target = f"https://{target}"

        try:
            parsed_url = urlparse(target)
            hostname = parsed_url.hostname
            parsed_url.port  # Accessing this validates an explicitly supplied port.
        except ValueError:
            return "Можно открывать только адреса сайтов с http или https."
        if (
            parsed_url.scheme not in {"http", "https"}
            or not hostname
            or any(character.isspace() for character in parsed_url.netloc)
        ):
            return "Можно открывать только адреса сайтов с http или https."
        return await self._open_url(target, f"Открываю сайт: {target}")

    async def _open_app(self, match: re.Match[str]) -> str:
        alias = RequestRecognizer.normalize(match.group("target"))
        command = self.apps.get(alias)
        if command is None:
            return f"Приложение «{alias}» отсутствует в списке разрешённых приложений."
        try:
            await asyncio.to_thread(self._launch_configured_app, command)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return f"Не удалось запустить «{alias}»: {error}"
        return f"Запускаю {alias}."

    @staticmethod
    def _launch_configured_app(command: str) -> None:
        """Launch only a command explicitly present in the trusted YAML config."""
        command = command.strip()
        if command.casefold().startswith("app:"):
            app_name = command[4:].strip()
            shortcut = ActionEngine._find_start_menu_shortcut(app_name)
            if shortcut is None:
                raise FileNotFoundError(f"ярлык {app_name!r} не найден")
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                raise OSError("ярлыки меню Пуск поддерживаются только в Windows")
            startfile(shortcut)
            return

        if command.casefold().startswith("start "):
            command = command[6:].strip()
        arguments = [part.strip('"') for part in shlex.split(command, posix=False)]
        if not arguments:
            raise ValueError("пустая команда запуска")
        if os.name == "nt" and ":" in arguments[0] and not Path(arguments[0]).exists():
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                raise OSError("системные URI поддерживаются только в Windows")
            startfile(arguments[0])
            return
        if len(arguments) == 1 and arguments[0].casefold().endswith(".lnk") and os.name == "nt":
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                raise OSError("ярлыки поддерживаются только в Windows")
            startfile(arguments[0])
            return
        subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )

    @staticmethod
    def _find_start_menu_shortcut(app_name: str) -> Path | None:
        roots = (
            Path(os.environ.get("ProgramData", "C:/ProgramData"))
            / "Microsoft/Windows/Start Menu/Programs",
            Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs",
        )
        wanted = app_name.casefold()
        for root in roots:
            if not root.is_dir():
                continue
            for shortcut in root.rglob("*.lnk"):
                if shortcut.stem.casefold() == wanted:
                    return shortcut
        return None

    async def _request_process_close(self, match: re.Match[str]) -> str:
        alias = RequestRecognizer.normalize(match.group("target"))
        if alias not in self.processes:
            return f"Процесс «{alias}» отсутствует в разрешённом списке."
        self._pending_process_close = (alias, time.monotonic() + 20)
        return (
            f"Закрыть процесс «{alias}»? Скажите «подтверждаю» в течение 20 секунд "
            "или «отмена»."
        )

    async def _terminate_configured_processes(self, alias: str) -> str:
        process_name = self.processes[alias].casefold()
        terminated = await asyncio.to_thread(self._terminate_processes, process_name)
        if terminated == 0:
            return f"Процесс «{alias}» не найден."
        return f"Отправлен запрос на закрытие процесса «{alias}»."

    @staticmethod
    def _terminate_processes(process_name: str) -> int:
        terminated = 0
        for process in psutil.process_iter(["name"]):
            try:
                if (process.info.get("name") or "").casefold() == process_name:
                    process.terminate()
                    terminated += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return terminated

    async def _run_safe_command(self, match: re.Match[str]) -> str:
        command = match.group("command").strip()
        if any(pattern.search(command) for pattern in self.blocked_patterns):
            return "Команда заблокирована политикой безопасности."
        if re.search(r"[\r\n;&|<>`]|\$\(", command):
            return "Команды оболочки с перенаправлением или цепочками запрещены."

        try:
            arguments = [part.strip('"') for part in shlex.split(command, posix=False)]
            safe_commands = {
                tuple(part.strip('"').casefold() for part in shlex.split(prefix, posix=False))
                for prefix in self.safe_commands
            }
        except ValueError:
            return "Не удалось разобрать команду."
        if not arguments or tuple(part.casefold() for part in arguments) not in safe_commands:
            return "Разрешены только команды, полностью перечисленные в shell.safe_prefixes."

        timeout = float(self.shell_config.get("timeout_s", 10))
        workdir = Path(self.shell_config.get("workdir", "."))
        if not workdir.is_absolute():
            workdir = self.config_path.parent / workdir
        command_name = arguments[0].casefold()
        if command_name in {"pwd", "whoami", "dir", "ls"} and len(arguments) == 1:
            if command_name == "pwd":
                output = str(workdir.resolve())
            elif command_name == "whoami":
                output = getpass.getuser()
            else:
                try:
                    output = "\n".join(sorted(item.name for item in workdir.iterdir()))
                except OSError as error:
                    return f"Не удалось прочитать каталог: {error}"
            self._write_audit_log(command, 0)
            return output or "Каталог пуст."
        if command_name in {"python", "python.exe"}:
            arguments[0] = sys.executable
        elif command_name == "pip":
            arguments[:1] = [sys.executable, "-m", "pip"]
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                arguments,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return f"Команда не выполнена: {error}"

        output = (result.stdout or result.stderr).strip()
        if len(output) > 2000:
            output = output[:2000] + "…"
        self._write_audit_log(command, result.returncode)
        return output or f"Команда завершилась с кодом {result.returncode}."

    def _write_audit_log(self, command: str, return_code: int) -> None:
        log_path = str(self.shell_config.get("audit_log", "")).strip()
        if not log_path:
            return
        path = Path(log_path)
        if not path.is_absolute():
            path = self.config_path.parent / path
        with path.open("a", encoding="utf-8") as log_file:
            log_file.write(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{return_code}\t{command}\n"
            )

    async def _open_url(self, url: str, success_message: str) -> str:
        try:
            opened = await asyncio.to_thread(webbrowser.open_new_tab, url)
        except (OSError, webbrowser.Error):
            return "Не удалось открыть браузер. Проверьте настройки браузера в системе."
        if not opened:
            return "Не удалось открыть браузер. Проверьте настройки браузера в системе."
        return success_message
