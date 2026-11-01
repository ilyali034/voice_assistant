from dataclasses import dataclass

import keyring
from PySide6.QtCore import QSettings


KEYRING_SERVICE = "voice-assistant-desktop"
KEYRING_USERNAME = "remote-backend-api-key"


@dataclass(frozen=True)
class DesktopSettings:
    backend_mode: str = "local"
    assistant_mode: str = "llm"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    remote_url: str = "http://127.0.0.1:8765"
    remote_api_key: str = ""
    language: str = "ru"
    speak_responses: bool = True


class SettingsStore:
    """Persist preferences with QSettings and keep the API key in OS keyring."""

    def __init__(self) -> None:
        self._settings = QSettings("VoiceAssistant", "DesktopClient")

    def load(self) -> DesktopSettings:
        try:
            api_key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or ""
        except keyring.errors.KeyringError:
            api_key = ""

        return DesktopSettings(
            backend_mode=str(self._settings.value("backend_mode", "local")),
            assistant_mode=str(self._settings.value("assistant_mode", "llm")),
            ollama_url=str(
                self._settings.value("ollama_url", "http://127.0.0.1:11434")
            ),
            ollama_model=str(self._settings.value("ollama_model", "llama3.2")),
            remote_url=str(
                self._settings.value("remote_url", "http://127.0.0.1:8765")
            ),
            remote_api_key=api_key,
            language=str(self._settings.value("language", "ru")),
            speak_responses=str(
                self._settings.value("speak_responses", True)
            ).casefold()
            in {"1", "true", "yes"},
        )

    def save(self, settings: DesktopSettings) -> None:
        if settings.remote_api_key.strip():
            keyring.set_password(
                KEYRING_SERVICE,
                KEYRING_USERNAME,
                settings.remote_api_key.strip(),
            )

        self._settings.setValue("backend_mode", settings.backend_mode)
        self._settings.setValue("assistant_mode", settings.assistant_mode)
        self._settings.setValue("ollama_url", settings.ollama_url)
        self._settings.setValue("ollama_model", settings.ollama_model)
        self._settings.setValue("remote_url", settings.remote_url)
        self._settings.setValue("language", settings.language)
        self._settings.setValue("speak_responses", settings.speak_responses)
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            raise RuntimeError("Не удалось сохранить настройки приложения.")

    def forget_api_key(self) -> None:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except keyring.errors.PasswordDeleteError:
            pass