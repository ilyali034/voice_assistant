import json
import unittest
from unittest.mock import patch

from core.main_engine.remote_client import RemoteResponseEngine


class RemoteResponseEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_authenticated_json_and_returns_response(self) -> None:
        engine = RemoteResponseEngine(
            "https://assistant.example/api/",
            "test-secret",
        )
        with patch.object(engine, "_post", return_value={"response": "  Hello  "}) as post:
            response = await engine.handle("  Hi  ")

        request = post.call_args.args[0]
        self.assertEqual(response, "Hello")
        self.assertEqual(request.full_url, "https://assistant.example/api/v1/requests")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(json.loads(request.data), {"request": "  Hi  "})

    async def test_invalid_backend_response_is_rejected(self) -> None:
        engine = RemoteResponseEngine("http://localhost:8765", "test-secret")
        with patch.object(engine, "_post", return_value={"answer": "missing key"}):
            with self.assertRaisesRegex(RuntimeError, "no string 'response'"):
                await engine.handle("hello")

    def test_rejects_non_http_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "absolute HTTP or HTTPS"):
            RemoteResponseEngine("file:///tmp/api", "test-secret")

    def test_requires_https_for_remote_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS is required"):
            RemoteResponseEngine("http://assistant.example", "test-secret")

    def test_allows_http_for_local_development(self) -> None:
        engine = RemoteResponseEngine("http://127.0.0.1:8765", "test-secret")

        self.assertEqual(engine.base_url, "http://127.0.0.1:8765")

    def test_rejects_missing_api_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "api_key must not be empty"):
            RemoteResponseEngine("http://localhost:8765", " ")


if __name__ == "__main__":
    unittest.main()