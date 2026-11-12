"""Environment-configured server entry point: ``python -m core.api.server``."""

import os

import uvicorn
from fastapi import FastAPI

from ..main_engine.assistant_service import AssistantService
from ..main_engine.llm.ollama_engine import OllamaResponseEngine
from .app import create_app
from .ollama_runtime import ensure_ollama


def create_server_app(api_key: str | None = None) -> FastAPI:
    """Build a text-only backend using the configured local Ollama instance."""
    resolved_api_key = api_key or os.environ.get("ASSISTANT_API_KEY", "")
    if not resolved_api_key.strip():
        raise ValueError("Set ASSISTANT_API_KEY before starting the backend")

    response_engine = OllamaResponseEngine(
        model=os.environ.get("ASSISTANT_MODEL", "llama3.2"),
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        timeout=float(os.environ.get("OLLAMA_TIMEOUT_S", "120")),
        lang=os.environ.get("ASSISTANT_LANGUAGE", "ru"),
    )
    service = AssistantService({"llm": response_engine})
    return create_app(service, resolved_api_key)


def main() -> None:
    if os.environ.get("ASSISTANT_MANAGE_OLLAMA") == "1":
        ensure_ollama(
            os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            os.environ.get("ASSISTANT_MODEL", "llama3.2"),
        )
    api = create_server_app()
    host = os.environ.get("ASSISTANT_HOST", "127.0.0.1")
    port = int(os.environ.get("ASSISTANT_PORT", "8765"))
    uvicorn.run(api, host=host, port=port)


if __name__ == "__main__":
    main()