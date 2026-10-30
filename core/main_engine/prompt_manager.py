from typing import Final


STANDARD_PROMPTS: Final[dict[str, str]] = {
    "assistant": (
        "Ты полезный голосовой ассистент. Отвечай понятно и по существу. "
        "Если не знаешь ответ, скажи об этом прямо. Язык ответа: {lang}."
    ),
    "concise": (
        "Отвечай кратко и прямо, обычно не более трёх предложений. "
        "Не добавляй вступления без необходимости. Язык ответа: {lang}."
    ),
    "tutor": (
        "Ты терпеливый преподаватель. Объясняй сложные темы простыми словами, "
        "по шагам и с короткими примерами. Язык ответа: {lang}."
    ),
    "programmer": (
        "Ты опытный помощник по программированию. Предлагай корректные и "
        "безопасные решения, кратко объясняй важные детали. Не утверждай, "
        "что код проверен, если он не запускался. Язык ответа: {lang}."
    ),
    "translator": (
        "Ты переводчик. Переводи текст пользователя на язык {lang}, сохраняя "
        "смысл и тон. Если пользователь явно указал другой язык перевода, "
        "следуй его указанию. Возвращай только перевод."
    ),
}


class PromptManager:
    """Select a built-in LLM prompt or use a user-written custom prompt."""

    def __init__(
        self,
        lang: str = "ru",
        preset: str = "assistant",
        custom_prompt: str | None = None,
    ) -> None:
        self.lang = lang
        self._preset = "assistant"
        self._custom_prompt: str | None = None
        self.select_preset(preset)
        if custom_prompt is not None:
            self.set_custom_prompt(custom_prompt)

    @property
    def available_presets(self) -> tuple[str, ...]:
        return tuple(STANDARD_PROMPTS)

    @property
    def selected_preset(self) -> str:
        return self._preset

    @property
    def is_custom(self) -> bool:
        return self._custom_prompt is not None

    @property
    def system_prompt(self) -> str:
        if self._custom_prompt is not None:
            return self._custom_prompt
        return STANDARD_PROMPTS[self._preset].format(lang=self.lang)

    def select_preset(self, preset: str) -> None:
        """Select a built-in prompt and clear any active custom prompt."""
        if preset not in STANDARD_PROMPTS:
            names = ", ".join(STANDARD_PROMPTS)
            raise ValueError(f"Unknown prompt preset {preset!r}. Available presets: {names}")
        self._preset = preset
        self._custom_prompt = None

    def set_custom_prompt(self, prompt: str) -> None:
        """Use a non-empty user-written system prompt."""
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Custom prompt must not be empty")
        self._custom_prompt = prompt

    def clear_custom_prompt(self) -> None:
        """Return to the currently selected built-in prompt."""
        self._custom_prompt = None
