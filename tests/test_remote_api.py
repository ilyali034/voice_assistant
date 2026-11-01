import unittest
from typing import Any

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.main_engine.assistant_service import AssistantService


class FakeResponseEngine:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.requests: list[str] = []

    async def handle(self, request: str) -> Any:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class RemoteApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = FakeResponseEngine("Hello from backend")
        service = AssistantService({"llm": self.engine})
        self.client = TestClient(create_app(service, "test-secret"))

    def test_health_is_available_without_authentication(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_request_requires_bearer_api_key(self) -> None:
        response = self.client.post("/v1/requests", json={"request": "hello"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.engine.requests, [])

    def test_authorized_request_is_dispatched(self) -> None:
        response = self.client.post(
            "/v1/requests",
            json={"request": "hello"},
            headers={"Authorization": "Bearer test-secret"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "Hello from backend"})
        self.assertEqual(self.engine.requests, ["hello"])

    def test_request_over_limit_is_rejected(self) -> None:
        response = self.client.post(
            "/v1/requests",
            json={"request": "x" * 1801},
            headers={"Authorization": "Bearer test-secret"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.engine.requests, [])

    def test_internal_error_is_not_returned_to_client(self) -> None:
        self.engine.response = RuntimeError("private model endpoint details")
        response = self.client.post(
            "/v1/requests",
            json={"request": "hello"},
            headers={"Authorization": "Bearer test-secret"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private model endpoint details", response.text)

    def test_empty_api_key_is_rejected(self) -> None:
        service = AssistantService({"llm": self.engine})

        with self.assertRaisesRegex(ValueError, "API key is required"):
            create_app(service, "  ")


if __name__ == "__main__":
    unittest.main()