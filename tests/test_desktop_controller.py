import unittest

from core.main_engine.response_engine import ActionEngine, OllamaResponseEngine
from desktop_client.controller import build_service
from desktop_client.settings import DesktopSettings
from core.main_engine.remote_client import RemoteResponseEngine


class DesktopControllerTests(unittest.TestCase):
    def test_local_mode_uses_ollama_and_local_actions(self) -> None:
        service = build_service(DesktopSettings())

        self.assertIsInstance(service.response_engines["llm"], OllamaResponseEngine)
        self.assertIsInstance(service.response_engines["actions"], ActionEngine)
        self.assertEqual(service.assistant_mode, "llm")

    def test_remote_mode_keeps_actions_on_desktop(self) -> None:
        service = build_service(
            DesktopSettings(
                backend_mode="remote",
                remote_url="https://assistant.example",
                remote_api_key="secret",
                assistant_mode="actions",
            )
        )

        self.assertIsInstance(service.response_engines["llm"], RemoteResponseEngine)
        self.assertIsInstance(service.response_engines["actions"], ActionEngine)
        self.assertEqual(service.assistant_mode, "actions")

    def test_remote_mode_requires_a_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "api_key must not be empty"):
            build_service(
                DesktopSettings(
                    backend_mode="remote",
                    remote_url="https://assistant.example",
                )
            )

    def test_local_mode_rejects_malformed_ollama_url(self) -> None:
        with self.assertRaisesRegex(ValueError, r"полный HTTP\(S\)-адрес"):
            build_service(DesktopSettings(ollama_url="not-a-url"))


if __name__ == "__main__":
    unittest.main()