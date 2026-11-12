import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.main_engine.llm.ollama_engine import OllamaResponseEngine


class OllamaHistorySearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_model_requests_search_by_default(self):
        engine = object.__new__(OllamaResponseEngine)
        search = AsyncMock(return_value="Липецк: +8 °C, облачно.")
        engine.search_engine = SimpleNamespace(standart_search=search)
        engine.prompt_manager = SimpleNamespace(lang="ru")
        engine._generate_response = AsyncMock(return_value="В Липецке +8 °C и облачно.")

        response = await engine.handle("Какая погода в Липецке?")

        self.assertEqual(response, "В Липецке +8 °C и облачно.")
        search.assert_awaited_once_with(request="Какая погода в Липецке?")
        user_content = engine._generate_response.await_args.args[0]
        self.assertIn("Липецк: +8 °C, облачно.", user_content)
        self.assertIn("Не говори, что у тебя нет доступа к интернету", user_content)

    async def test_history_requests_include_fresh_search_context(self):
        engine = object.__new__(OllamaResponseEngine)
        search = AsyncMock(return_value="Актуальная погода: +8 °C, облачно.")
        engine.search_engine = SimpleNamespace(standart_search=search)
        engine.prompt_manager = SimpleNamespace(lang="ru")
        engine._generate_response = AsyncMock(return_value="Сейчас +8 °C и облачно.")
        history = [{"role": "user", "content": "Привет"}]

        response = await engine.handle_with_history("Какая погода в Липецке?", history)

        self.assertEqual(response, "Сейчас +8 °C и облачно.")
        search.assert_awaited_once_with(request="Какая погода в Липецке?")
        user_content, supplied_history = engine._generate_response.await_args.args
        self.assertIn("Актуальная погода: +8 °C, облачно.", user_content)
        self.assertIn("Какая погода в Липецке?", user_content)
        self.assertEqual(supplied_history, history)

    async def test_search_failure_still_generates_an_answer_with_a_caveat(self):
        engine = object.__new__(OllamaResponseEngine)
        search = AsyncMock(side_effect=TimeoutError("search timed out"))
        engine.search_engine = SimpleNamespace(standart_search=search)
        engine.prompt_manager = SimpleNamespace(lang="ru")
        engine._generate_response = AsyncMock(return_value="Не могу проверить текущую погоду.")

        response = await engine.handle_with_history("Какая погода в Липецке?", [])

        self.assertEqual(response, "Не могу проверить текущую погоду.")
        user_content = engine._generate_response.await_args.args[0]
        self.assertIn("не вернул актуальных данных", user_content)
        self.assertIn("не выдумывай", user_content.casefold())


if __name__ == "__main__":
    unittest.main()
