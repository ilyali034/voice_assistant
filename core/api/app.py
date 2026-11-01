import hmac
import logging
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from ..main_engine.assistant_service import AssistantService


logger = logging.getLogger(__name__)
MAX_REQUEST_CHARS = 1800


class AssistantRequest(BaseModel):
    request: str = Field(min_length=1, max_length=MAX_REQUEST_CHARS)


class AssistantResponse(BaseModel):
    response: str


def create_app(service: AssistantService, api_key: str) -> FastAPI:
    """Create an authenticated API app around a text-only assistant service."""
    expected_api_key = api_key.strip()
    if not expected_api_key:
        raise ValueError("An API key is required to expose the assistant backend")

    app = FastAPI(title="Voice Assistant API", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/requests", response_model=AssistantResponse)
    async def handle_request(
        payload: AssistantRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> AssistantResponse:
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

        try:
            response = await service.handle_request(payload.request)
        except Exception as error:
            logger.exception("Assistant backend failed to process a request")
            raise HTTPException(
                status_code=502,
                detail="The assistant backend failed to process the request.",
            ) from error
        return AssistantResponse(response=response)

    return app