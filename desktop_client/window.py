import asyncio
import html
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.main_engine.assistant_service import AssistantService

from .controller import build_service
from .settings import DesktopSettings, SettingsStore
from .voice import LocalVoiceInput


class _RequestSignals(QObject):
    response_ready = Signal(str)
    failed = Signal(str)
    speech_failed = Signal(str)
    finished = Signal()


class _VoiceSignals(QObject):
    status = Signal(str)
    recognized = Signal(str)
    failed = Signal(str)
    finished = Signal()


class _RequestWorker(QRunnable):
    def __init__(
        self,
        service: AssistantService,
        request: str,
        *,
        speak_response: bool,
        language: str,
    ) -> None:
        super().__init__()
        self.service = service
        self.request = request
        self.speak_response = speak_response
        self.language = language
        self.signals = _RequestSignals()

    def run(self) -> None:
        async def process_request() -> None:
            response = await self.service.handle_request(self.request)
            self.signals.response_ready.emit(response)
            if self.speak_response and response:
                try:
                    from core.main_engine.voice_engine.assi_voice import AsyncSpeechEngine

                    speaker = AsyncSpeechEngine(mode="offline", lang=self.language)
                    await speaker.say(response)
                except Exception as error:
                    self.signals.speech_failed.emit(str(error))

        try:
            asyncio.run(process_request())
        except Exception as error:
            self.signals.failed.emit(str(error))
        finally:
            self.signals.finished.emit()


class _VoiceCaptureWorker(QRunnable):
    def __init__(
        self,
        voice_input: LocalVoiceInput,
        stop_event: threading.Event,
        language: str,
    ) -> None:
        super().__init__()
        self.voice_input = voice_input
        self.stop_event = stop_event
        self.language = language
        self.signals = _VoiceSignals()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        try:
            request = self.voice_input.transcribe_until_silence(
                self.stop_event,
                language=self.language,
                on_status=self.signals.status.emit,
            )
        except Exception as error:
            self.signals.failed.emit(str(error))
        else:
            self.signals.recognized.emit(request)
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings_store: SettingsStore | None = None,
        *,
        service_factory: Callable[[DesktopSettings], AssistantService] = build_service,
    ) -> None:
        super().__init__()
        self.settings_store = settings_store or SettingsStore()
        self.service_factory = service_factory
        self.settings = self.settings_store.load()
        self.service: AssistantService | None = None
        self._active_worker: _RequestWorker | None = None
        self._voice_worker: _VoiceCaptureWorker | None = None
        self._pending_voice_request = ""
        self._voice_input = LocalVoiceInput()
        self._thread_pool = QThreadPool.globalInstance()

        self.setWindowTitle("Voice Assistant")
        self.resize(1040, 760)
        self.setMinimumSize(780, 600)
        self._build_ui()
        self._load_settings_into_form(self.settings)
        self.apply_settings(show_dialog=False)
        self._append_message(
            "assistant",
            "Привет! Выберите локальную модель или backend-сервер и отправьте запрос.",
        )

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        header = QHBoxLayout()
        brand = QVBoxLayout()
        title = QLabel("VOICE ASSISTANT")
        title.setObjectName("appTitle")
        subtitle = QLabel("Локальный помощник · защищённое подключение к серверу")
        subtitle.setObjectName("subtitle")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch(1)
        self.connection_badge = QLabel("НАСТРОЙКА")
        self.connection_badge.setObjectName("statusBadge")
        header.addWidget(self.connection_badge, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        settings_card = QFrame()
        settings_card.setObjectName("card")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(18, 16, 18, 16)
        settings_layout.setSpacing(12)

        settings_title = QLabel("Подключение")
        settings_title.setObjectName("sectionTitle")
        settings_layout.addWidget(settings_title)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.backend_mode = QComboBox()
        self.backend_mode.addItem("Локально · Ollama на ноутбуке", "local")
        self.backend_mode.addItem("Удалённый backend · сервер", "remote")
        form.addRow("Где работает LLM", self.backend_mode)

        self.local_fields = QWidget()
        local_form = QFormLayout(self.local_fields)
        local_form.setContentsMargins(0, 0, 0, 0)
        local_form.setHorizontalSpacing(18)
        local_form.setVerticalSpacing(8)
        self.ollama_url = QLineEdit()
        self.ollama_url.setPlaceholderText("http://127.0.0.1:11434")
        self.ollama_model = QLineEdit()
        self.ollama_model.setPlaceholderText("llama3.2")
        local_form.addRow("Адрес Ollama", self.ollama_url)
        local_form.addRow("Модель", self.ollama_model)
        form.addRow("", self.local_fields)

        self.remote_fields = QWidget()
        remote_form = QFormLayout(self.remote_fields)
        remote_form.setContentsMargins(0, 0, 0, 0)
        remote_form.setHorizontalSpacing(18)
        remote_form.setVerticalSpacing(8)
        self.remote_url = QLineEdit()
        self.remote_url.setPlaceholderText("https://assistant.example")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Ключ хранится в системном хранилище паролей")
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.api_key, 1)
        self.forget_key_button = QPushButton("Забыть ключ")
        self.forget_key_button.setObjectName("secondaryButton")
        key_layout.addWidget(self.forget_key_button)
        remote_form.addRow("Адрес backend", self.remote_url)
        remote_form.addRow("API key", key_row)
        form.addRow("", self.remote_fields)

        self.assistant_mode = QComboBox()
        self.assistant_mode.addItem("Диалог · LLM", "llm")
        self.assistant_mode.addItem("Команды · локально на ноутбуке", "actions")
        form.addRow("Обработка запроса", self.assistant_mode)
        settings_layout.addLayout(form)

        footer = QHBoxLayout()
        self.settings_status = QLabel()
        self.settings_status.setWordWrap(True)
        self.settings_status.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        footer.addWidget(self.settings_status, 1)
        self.apply_button = QPushButton("Сохранить и подключить")
        self.apply_button.setObjectName("primaryButton")
        footer.addWidget(self.apply_button)
        settings_layout.addLayout(footer)
        root.addWidget(settings_card)

        chat_card = QFrame()
        chat_card.setObjectName("card")
        chat_layout = QVBoxLayout(chat_card)
        chat_layout.setContentsMargins(18, 16, 18, 16)
        chat_layout.setSpacing(12)
        chat_heading = QHBoxLayout()
        chat_label = QLabel("Диалог")
        chat_label.setObjectName("sectionTitle")
        chat_heading.addWidget(chat_label)
        chat_heading.addStretch(1)
        self.mode_label = QLabel()
        self.mode_label.setObjectName("modeLabel")
        chat_heading.addWidget(self.mode_label)
        self.voice_status = QLabel()
        self.voice_status.setObjectName("voiceStatus")
        chat_heading.addWidget(self.voice_status)
        chat_layout.addLayout(chat_heading)

        self.chat = QTextBrowser()
        self.chat.setObjectName("chatView")
        self.chat.setOpenExternalLinks(False)
        self.chat.setMinimumHeight(260)
        chat_layout.addWidget(self.chat, 1)

        composer = QHBoxLayout()
        composer.setSpacing(10)
        self.request_input = QLineEdit()
        self.request_input.setObjectName("requestInput")
        self.request_input.setPlaceholderText("Напишите запрос или используйте микрофон…")
        self.mic_button = QPushButton("🎙 Голос")
        self.mic_button.setObjectName("micButton")
        self.mic_button.setCheckable(True)
        self.mic_button.setToolTip(
            "Начать/остановить локальную запись. F9 работает, пока окно активно."
        )
        self.speak_checkbox = QCheckBox("Озвучивать ответ")
        self.send_button = QPushButton("Отправить")
        self.send_button.setObjectName("primaryButton")
        composer.addWidget(self.request_input, 1)
        composer.addWidget(self.mic_button)
        composer.addWidget(self.speak_checkbox)
        composer.addWidget(self.send_button)
        chat_layout.addLayout(composer)
        root.addWidget(chat_card, 1)

        self.setCentralWidget(central)
        self.setStyleSheet(_STYLESHEET)
        self.voice_hotkey = QShortcut(QKeySequence("F9"), self)
        self.backend_mode.currentIndexChanged.connect(self._update_backend_fields)
        self.assistant_mode.currentIndexChanged.connect(self._update_backend_fields)
        self.apply_button.clicked.connect(self.apply_settings)
        self.forget_key_button.clicked.connect(self.forget_api_key)
        self.mic_button.toggled.connect(self._toggle_voice_capture)
        self.voice_hotkey.activated.connect(self._toggle_voice_hotkey)
        self.send_button.clicked.connect(self.send_request)
        self.request_input.returnPressed.connect(self.send_request)
        self._update_backend_fields()

    def _load_settings_into_form(self, settings: DesktopSettings) -> None:
        self._set_combo_data(self.backend_mode, settings.backend_mode)
        self._set_combo_data(self.assistant_mode, settings.assistant_mode)
        self.ollama_url.setText(settings.ollama_url)
        self.ollama_model.setText(settings.ollama_model)
        self.remote_url.setText(settings.remote_url)
        self.api_key.setText(settings.remote_api_key)
        self.speak_checkbox.setChecked(settings.speak_responses)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _update_backend_fields(self, *_: object) -> None:
        is_local = self.backend_mode.currentData() == "local"
        self.local_fields.setVisible(is_local)
        self.remote_fields.setVisible(not is_local)
        self.mode_label.setText(
            "ДЕЙСТВИЯ ВЫПОЛНЯЮТСЯ НА ЭТОМ ПК"
            if self.assistant_mode.currentData() == "actions"
            else ("ЛОКАЛЬНАЯ МОДЕЛЬ" if is_local else "ЗАПРОСЫ ИДУТ НА BACKEND")
        )

    def _read_settings(self) -> DesktopSettings:
        return DesktopSettings(
            backend_mode=str(self.backend_mode.currentData()),
            assistant_mode=str(self.assistant_mode.currentData()),
            ollama_url=self.ollama_url.text().strip(),
            ollama_model=self.ollama_model.text().strip(),
            remote_url=self.remote_url.text().strip(),
            remote_api_key=self.api_key.text(),
            language=self.settings.language,
            speak_responses=self.speak_checkbox.isChecked(),
        )

    def apply_settings(self, *_: object, show_dialog: bool = True) -> None:
        candidate = self._read_settings()
        try:
            service = self.service_factory(candidate)
            self.settings_store.save(candidate)
        except Exception as error:
            self.service = None
            self.send_button.setEnabled(False)
            self.connection_badge.setText("НЕ ПОДКЛЮЧЕНО")
            self.connection_badge.setProperty("state", "error")
            self.connection_badge.style().unpolish(self.connection_badge)
            self.connection_badge.style().polish(self.connection_badge)
            self.settings_status.setText(str(error))
            self.settings_status.setStyleSheet("color: #fca5a5;")
            if show_dialog:
                QMessageBox.warning(self, "Не удалось подключиться", str(error))
            return

        self.settings = candidate
        self.service = service
        self.send_button.setEnabled(True)
        self.connection_badge.setText(
            "ЛОКАЛЬНО" if candidate.backend_mode == "local" else "REMOTE"
        )
        self.connection_badge.setProperty("state", "ready")
        self.connection_badge.style().unpolish(self.connection_badge)
        self.connection_badge.style().polish(self.connection_badge)
        self.settings_status.setText("Настройки применены. Запросы готовы к отправке.")
        self.settings_status.setStyleSheet("color: #6ee7b7;")
        if show_dialog:
            self.statusBar().showMessage("Настройки применены", 3000)
        self._update_backend_fields()

    def forget_api_key(self) -> None:
        try:
            self.settings_store.forget_api_key()
        except Exception as error:
            QMessageBox.warning(self, "Хранилище ключей", str(error))
            return
        self.api_key.clear()
        if self.backend_mode.currentData() == "remote":
            self.apply_settings(show_dialog=False)
        self.settings_status.setText("Ключ удалён из системного хранилища.")

    def send_request(self) -> None:
        request = self.request_input.text().strip()
        self._start_request(request, speak_response=self.speak_checkbox.isChecked())

    def _start_request(self, request: str, *, speak_response: bool) -> None:
        if (
            not request
            or self.service is None
            or self._active_worker is not None
            or self._voice_worker is not None
        ):
            return

        self._append_message("user", request)
        self.request_input.clear()
        self._set_busy(True)
        worker = _RequestWorker(
            self.service,
            request,
            speak_response=speak_response,
            language=self.settings.language,
        )
        self._active_worker = worker
        worker.signals.response_ready.connect(self._request_succeeded)
        worker.signals.failed.connect(self._request_failed)
        worker.signals.speech_failed.connect(self._speech_failed)
        worker.signals.finished.connect(self._finish_request)
        self._thread_pool.start(worker)

    def _request_succeeded(self, response: str) -> None:
        self._append_message("assistant", response or "(пустой ответ)")

    def _request_failed(self, error: str) -> None:
        self._append_message("error", error)

    def _speech_failed(self, error: str) -> None:
        self.voice_status.setText(f"Ответ показан, но TTS не сработал: {error}")

    def _finish_request(self) -> None:
        self._active_worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.send_button.setEnabled(not busy and self.service is not None)
        self.apply_button.setEnabled(not busy)
        self.request_input.setEnabled(not busy)
        self.mic_button.setEnabled(not busy)
        self.speak_checkbox.setEnabled(not busy)
        self.send_button.setText("Обработка…" if busy else "Отправить")

    def _toggle_voice_capture(self, checked: bool) -> None:
        if checked:
            if self.service is None or self._active_worker is not None:
                self._set_mic_checked(False)
                return

            self._pending_voice_request = ""
            worker = _VoiceCaptureWorker(
                self._voice_input,
                threading.Event(),
                self.settings.language,
            )
            self._voice_worker = worker
            worker.signals.status.connect(self.voice_status.setText)
            worker.signals.recognized.connect(self._voice_recognized)
            worker.signals.failed.connect(self._voice_failed)
            worker.signals.finished.connect(self._voice_finished)
            self.mic_button.setText("Остановить запись")
            self.send_button.setEnabled(False)
            self.request_input.setEnabled(False)
            self.apply_button.setEnabled(False)
            self.speak_checkbox.setEnabled(False)
            self._thread_pool.start(worker)
            return

        if self._voice_worker is not None:
            self.voice_status.setText("Останавливаю запись…")
            self.mic_button.setText("Завершение…")
            self.mic_button.setEnabled(False)
            self._voice_worker.stop()

    def _toggle_voice_hotkey(self) -> None:
        if self.mic_button.isEnabled():
            self.mic_button.setChecked(not self.mic_button.isChecked())

    def _voice_recognized(self, request: str) -> None:
        self._pending_voice_request = request.strip()

    def _voice_failed(self, error: str) -> None:
        self.voice_status.setText(f"Ошибка микрофона/STT: {error}")

    def _voice_finished(self) -> None:
        request = self._pending_voice_request
        self._pending_voice_request = ""
        self._voice_worker = None
        self._set_mic_checked(False)
        self.mic_button.setEnabled(True)
        self.request_input.setEnabled(True)
        self.apply_button.setEnabled(True)
        self.speak_checkbox.setEnabled(True)
        if request:
            self.voice_status.setText("Речь распознана; отправляю запрос…")
            self._start_request(
                request,
                speak_response=self.speak_checkbox.isChecked(),
            )
        elif not self.voice_status.text().startswith("Ошибка"):
            self.voice_status.setText("Речь не распознана.")

    def _set_mic_checked(self, checked: bool) -> None:
        self.mic_button.blockSignals(True)
        self.mic_button.setChecked(checked)
        self.mic_button.blockSignals(False)
        self.mic_button.setText("Остановить запись" if checked else "🎙 Голос")

    def _append_message(self, role: str, message: str) -> None:
        styles = {
            "user": ("Вы", "#a5b4fc", "#1c2340"),
            "assistant": ("Ассистент", "#6ee7b7", "#172b2a"),
            "error": ("Ошибка", "#fca5a5", "#351f27"),
        }
        title, accent, background = styles[role]
        safe_message = html.escape(message).replace("\n", "<br>")
        self.chat.append(
            f'<div style="margin: 8px 0; padding: 12px 14px; '
            f'background: {background}; border-radius: 12px;">'
            f'<span style="color: {accent}; font-weight: 700;">{title}</span>'
            f'<div style="color: #e5e7eb; margin-top: 5px;">{safe_message}</div>'
            "</div>"
        )
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._voice_worker is not None:
            self._voice_worker.stop()
        if self._active_worker is not None or self._voice_worker is not None:
            self._thread_pool.waitForDone(3000)
        event.accept()


_STYLESHEET = """
QMainWindow, QWidget { background: #0b1020; color: #e5e7eb; font-family: Segoe UI; font-size: 10pt; }
QFrame#card { background: #111827; border: 1px solid #263244; border-radius: 16px; }
QLabel#appTitle { color: #f8fafc; font-size: 20pt; font-weight: 800; letter-spacing: 2px; }
QLabel#subtitle { color: #94a3b8; font-size: 9pt; }
QLabel#sectionTitle { color: #f8fafc; font-size: 12pt; font-weight: 700; }
QLabel#modeLabel { color: #94a3b8; font-size: 8pt; font-weight: 700; }
QLabel#statusBadge { color: #c4b5fd; background: #241e3e; border-radius: 10px; padding: 7px 11px; font-size: 8pt; font-weight: 800; }
QLabel#statusBadge[state="ready"] { color: #6ee7b7; background: #12352d; }
QLabel#statusBadge[state="error"] { color: #fca5a5; background: #3b2028; }
QLineEdit, QComboBox { background: #0b1220; border: 1px solid #334155; border-radius: 9px; padding: 9px 11px; color: #f1f5f9; selection-background-color: #4f46e5; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #818cf8; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #111827; color: #f1f5f9; selection-background-color: #3730a3; }
QPushButton { border: none; border-radius: 9px; padding: 10px 15px; font-weight: 700; }
QPushButton#primaryButton { color: white; background: #4f46e5; }
QPushButton#primaryButton:hover { background: #6366f1; }
QPushButton#primaryButton:disabled { background: #334155; color: #94a3b8; }
QPushButton#secondaryButton, QPushButton#micButton { color: #cbd5e1; background: #263244; padding: 8px 10px; }
QPushButton#secondaryButton:hover { background: #334155; }
QPushButton#micButton:hover { background: #334155; }
QPushButton#micButton:checked { color: white; background: #b91c1c; }
QLabel#voiceStatus { color: #a5b4fc; font-size: 8pt; }
QCheckBox { color: #cbd5e1; spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QTextBrowser#chatView { background: #0b1220; border: 1px solid #263244; border-radius: 12px; padding: 10px; }
QLineEdit#requestInput { min-height: 24px; }
QStatusBar { color: #94a3b8; background: #0b1020; }
"""