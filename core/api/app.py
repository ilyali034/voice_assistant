import asyncio
import hmac
import logging
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..main_engine.assistant_service import AssistantService


logger = logging.getLogger(__name__)
MAX_REQUEST_CHARS = 1800


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_REQUEST_CHARS)


class AssistantRequest(BaseModel):
    request: str = Field(min_length=1, max_length=MAX_REQUEST_CHARS)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=20)


class AssistantResponse(BaseModel):
    response: str


class VoiceTextResponse(BaseModel):
    text: str


class VoiceSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class WakeWordRequest(BaseModel):
    wake_word: str = Field(min_length=1, max_length=40)


class WakeWordResponse(BaseModel):
    detected: bool


def create_app(service: AssistantService, api_key: str) -> FastAPI:
    """Create an authenticated assistant API with optional lazy-loaded voice support."""
    expected_api_key = api_key.strip()
    if not expected_api_key:
        raise ValueError("An API key is required to expose the assistant backend")

    app = FastAPI(title="Voice Assistant API", version="1.0.0")
    voice_lock = asyncio.Lock()
    voice_modules: dict[str, Any] = {}

    def authorize(authorization: str | None) -> None:
        scheme, separator, supplied_api_key = (authorization or "").partition(" ")
        if (
            not separator
            or scheme.casefold() != "bearer"
            or not hmac.compare_digest(supplied_api_key.strip(), expected_api_key)
        ):
            raise HTTPException(
                status_code=401,
                detail="A valid Bearer API key is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def get_voice_module(name: str) -> Any:
        if name == "wake":
            recognizer = await get_voice_module("recognition")
            async with voice_lock:
                if name not in voice_modules:
                    try:
                        from ..main_engine.voice_engine.voice import WakeUpModule

                        voice_modules[name] = await asyncio.to_thread(
                            WakeUpModule,
                            model=recognizer.model,
                        )
                    except Exception as error:
                        logger.exception("Could not initialize wake-word module")
                        raise HTTPException(
                            status_code=503,
                            detail=f"Не удалось запустить wake word: {error}",
                        ) from error
                return voice_modules[name]

        async with voice_lock:
            if name not in voice_modules:
                try:
                    from ..main_engine.voice_engine.voice import VoiceRecognition, VoiceTTSModule

                    module_type = VoiceRecognition if name == "recognition" else VoiceTTSModule
                    voice_modules[name] = await asyncio.to_thread(module_type)
                except Exception as error:
                    logger.exception("Could not initialize voice module: %s", name)
                    raise HTTPException(
                        status_code=503,
                        detail=f"Не удалось запустить голосовой модуль: {error}",
                    ) from error
            return voice_modules[name]

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/requests", response_model=AssistantResponse)
    async def handle_request(
        payload: AssistantRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> AssistantResponse:
        authorize(authorization)

        try:
            history = [turn.model_dump() for turn in payload.history]
            response = await service.handle_request(payload.request, history=history)
        except Exception as error:
            logger.exception("Assistant backend failed to process a request")
            raise HTTPException(
                status_code=502,
                detail="The assistant backend failed to process the request.",
            ) from error
        return AssistantResponse(response=response)

    @app.post("/v1/voice/listen", response_model=VoiceTextResponse)
    async def listen_for_voice(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> VoiceTextResponse:
        authorize(authorization)
        recognizer = await get_voice_module("recognition")
        recognition_task = asyncio.create_task(recognizer.start_recognize())
        try:
            deadline = asyncio.get_running_loop().time() + 60
            while not recognition_task.done():
                await asyncio.wait({recognition_task}, timeout=0.25)
                if await request.is_disconnected() or asyncio.get_running_loop().time() >= deadline:
                    recognition_task.cancel()
                    await asyncio.gather(recognition_task, return_exceptions=True)
                    return VoiceTextResponse(text="")
            text = await recognition_task
        except Exception as error:
            logger.exception("Voice recognition failed")
            raise HTTPException(status_code=503, detail=f"Ошибка микрофона: {error}") from error
        return VoiceTextResponse(text=text)

    @app.post("/v1/voice/wake", response_model=WakeWordResponse)
    async def wait_for_wake_word(
        payload: WakeWordRequest,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> WakeWordResponse:
        authorize(authorization)
        wake_module = await get_voice_module("wake")
        wake_task = asyncio.create_task(
            wake_module.recognize_wake_up_word(payload.wake_word.strip())
        )
        try:
            while not wake_task.done():
                await asyncio.wait({wake_task}, timeout=0.25)
                if await request.is_disconnected():
                    wake_task.cancel()
                    await asyncio.gather(wake_task, return_exceptions=True)
                    return WakeWordResponse(detected=False)
            return WakeWordResponse(detected=await wake_task)
        except Exception as error:
            logger.exception("Wake-word recognition failed")
            raise HTTPException(status_code=503, detail=f"Ошибка wake word: {error}") from error

    @app.post("/v1/voice/speak")
    async def speak_text(
        payload: VoiceSpeakRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        authorize(authorization)
        tts = await get_voice_module("tts")
        try:
            await tts.say(payload.text)
        except Exception as error:
            logger.exception("Text-to-speech failed")
            raise HTTPException(status_code=503, detail=f"Ошибка синтеза речи: {error}") from error
        return {"status": "ok"}

    @app.post("/v1/voice/stop")
    async def stop_speaking(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        authorize(authorization)
        tts = await get_voice_module("tts")
        tts.stop()
        return {"status": "stopping"}

    return app