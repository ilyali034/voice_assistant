import unittest
from typing import Any

from core.main_engine.assistant_service import AssistantService


class FakeResponseEngine:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.requests: list[str] = []

    async def handle(self, request: str) -> str:
        self.requests.append(request)
        return self.response


class AssistantServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_to_selected_engine_and_strips_result(self) -> None:
        llm = FakeResponseEngine("  hello  ")
        actions = FakeResponseEngine("  done  ")
        service = AssistantService({"llm": llm, "actions": actions})

        service.select_mode("actions")
        result = await service.handle_request("  open browser  ")

        self.assertEqual(result, "done")
        self.assertEqual(actions.requests, ["open browser"])
        self.assertEqual(llm.requests, [])

    async def test_empty_request_is_not_dispatched(self) -> None:
        engine = FakeResponseEngine("unused")
        service = AssistantService({"llm": engine})

        result = await service.handle_request(" \t ")

        self.assertEqual(result, "")
        self.assertEqual(engine.requests, [])

    async def test_rejects_unavailable_mode(self) -> None:
        service = AssistantService({"llm": FakeResponseEngine("ok")})

        with self.assertRaisesRegex(ValueError, "Available modes: llm"):
            service.select_mode("actions")

    async def test_rejects_empty_engine_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one response engine"):
            AssistantService({})

    async def test_rejects_non_string_response(self) -> None:
        service = AssistantService({"llm": FakeResponseEngine(None)})

        with self.assertRaisesRegex(TypeError, "must return a string"):
            await service.handle_request("hello")


if __name__ == "__main__":
    unittest.main()