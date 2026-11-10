from collections.abc import Mapping
from typing import Protocol


class ResponseEngine(Protocol):
    async def handle(self, request: str, web_search: bool = False) -> str:
        """Handle a user request and return a user-facing result."""


class AssistantService:
    """Text-only assistant orchestration, independent of local devices."""

    def __init__(
        self,
        response_engines: Mapping[str, ResponseEngine],
        assistant_mode: str = "llm",
    ) -> None:
        if not response_engines:
            raise ValueError("At least one response engine must be configured")

        self.response_engines = dict(response_engines)
        self._assistant_mode = ""
        self.select_mode(assistant_mode)

    @property
    def assistant_mode(self) -> str:
        return self._assistant_mode

    def select_mode(self, mode: str) -> None:
        """Select an available response engine by its configured name."""
        if mode not in self.response_engines:
            available = ", ".join(sorted(self.response_engines))
            raise ValueError(
                f"Unsupported assistant mode: {mode}. Available modes: {available}"
            )
        self._assistant_mode = mode

    async def handle_request(self, request: str) -> str:
        """Normalize and dispatch text without recording audio or speaking."""
        request = request.strip()
        if not request:
            return ""

        response = await self.response_engines[self._assistant_mode].handle(request)
        if not isinstance(response, str):
            raise TypeError("The selected response engine must return a string")
        return response.strip()