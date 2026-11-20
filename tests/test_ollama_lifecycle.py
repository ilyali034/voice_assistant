import asyncio
import subprocess
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.main_engine.engine import AssistentEngine
from core.main_engine.llm.ollama_engine import OllamaResponseEngine
from core.main_engine.llm.search_tools.search_engine import LangchainOllamaSearchEngine


class OllamaLifecycleTests(unittest.TestCase):
    def test_ensure_ollama_server_starts_for_local_llm_modes(self):
        engine = object.__new__(AssistentEngine)
        engine.llm_engine = object.__new__(OllamaResponseEngine)
        engine.llm_engine.base_url = "http://localhost:11434"
        engine.service = Mock()
        engine.service.assistant_mode = "hybrid"
        engine._ollama_server_process = None

        fake_process = Mock()
        fake_process.poll.return_value = None

        with patch("core.main_engine.engine.shutil.which", return_value="ollama"), patch(
            "core.main_engine.engine.subprocess.Popen", return_value=fake_process
        ) as popen_mock, patch(
            "core.main_engine.engine.AssistentEngine._wait_for_ollama_server",
            return_value=None,
        ):
            engine._ensure_ollama_server_running()

        popen_mock.assert_called_once_with(
            ["ollama", "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        self.assertIs(engine._ollama_server_process, fake_process)

    def test_stop_ollama_server_terminates_process(self):
        engine = object.__new__(AssistentEngine)
        process = Mock()
        process.poll.return_value = None
        engine._ollama_server_process = process

        engine._stop_ollama_server()

        process.terminate.assert_called_once()
        self.assertIsNone(engine._ollama_server_process)

    def test_search_timeout_returns_empty_context_without_crashing(self):
        engine = LangchainOllamaSearchEngine()

        with patch(
            "core.main_engine.llm.search_tools.search_engine.DDGS",
            side_effect=TimeoutError("timed out"),
        ):
            result = asyncio.run(engine.standart_search("какая погода в липецке"))

        self.assertIsInstance(result, str)
        self.assertEqual(result, "")

    def test_request_language_is_detected_for_search_locale(self):
        engine = object.__new__(OllamaResponseEngine)
        engine.lang = "ru"

        self.assertEqual(engine._detect_request_language("Какая погода сегодня?"), "ru")
        self.assertEqual(engine._detect_request_language("What is the weather today?"), "en")
        self.assertEqual(engine._detect_request_language("Який сьогодні стан погоди?"), "uk")


if __name__ == "__main__":
    unittest.main()
