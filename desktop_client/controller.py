from urllib.parse import urlparse

from core.main_engine.assistant_service import AssistantService
from core.main_engine.remote_client import RemoteResponseEngine
from core.main_engine.response_engine import ActionEngine, OllamaResponseEngine

from .settings import DesktopSettings


def build_service(settings: DesktopSettings) -> AssistantService:
    """Build local or remote LLM routing while keeping desktop actions local."""
    if settings.backend_mode == "local":
        ollama_url = settings.ollama_url.strip()
        parsed_url = urlparse(ollama_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("Укажите полный HTTP(S)-адрес локальной Ollama.")
        if parsed_url.username or parsed_url.password:
            raise ValueError("Не указывайте учётные данные внутри URL Ollama.")
        try:
            parsed_url.port
        except ValueError as error:
            raise ValueError("В адресе Ollama указан некорректный порт.") from error

        llm_engine = OllamaResponseEngine(
            model=settings.ollama_model.strip() or "llama3.2",
            base_url=ollama_url,
            lang=settings.language,
        )
    elif settings.backend_mode == "remote":
        llm_engine = RemoteResponseEngine(
            base_url=settings.remote_url.strip(),
            api_key=settings.remote_api_key,
        )
    else:
        raise ValueError(f"Неизвестный режим backend: {settings.backend_mode}")

    action_engine = ActionEngine()
    return AssistantService(
        {"llm": llm_engine, "actions": action_engine},
        assistant_mode=settings.assistant_mode,
    )