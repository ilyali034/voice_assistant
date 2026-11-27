"""Переводы интерфейса: ru / en."""

LANGS = {"ru": "Русский", "en": "English"}

DEFAULTS = {
    "ru": {"wake": "ассистент", "city": "Москва"},
    "en": {"wake": "assistant", "city": "London"},
}

STR = {
    "ru": {
        "title": "Голосовой ассистент",
        "brand": "АССИСТЕНТ",
        "online": "Онлайн",
        "loading": "Загрузка",
        "settings": "Настройки",
        "refresh": "Обновить",
        "system": "Система",
        "weather": "Погода",
        "camera": "Камера",
        "cam_toggle": "Включить / выключить камеру",
        "cam_off": "Камера выключена",
        "cam_missing": "Модуль QtMultimedia недоступен.",
        "cam_none": "Камера не найдена.",
        "cam_error": "Ошибка камеры.",
        "uptime": "Время работы",
        "cpu_name": "Процессор",
        "mem_name": "Память",
        "load": "Нагрузка",
        "tile_cpu": "ЦП",
        "tile_ram": "ОЗУ",
        "tile_disk": "Диск",
        "tile_hum": "Влажность",
        "tile_wind": "Ветер",
        "tile_feels": "Ощущается",
        "tile_msgs": "Сообщений",
        "tile_lat": "Задержка",
        "gb": "ГБ",
        "sec": "с",
        "ms": "м/с",
        "load_low": "Низкая",
        "load_mid": "Средняя",
        "load_high": "Высокая",
        "chat": "Диалог",
        "clear": "Очистить",
        "export": "Экспорт",
        "placeholder": "Напишите сообщение…",
        "send": "Отправить",
        "mic_tip": "Слушать слово активации",
        "tts_tip": "Озвучивать ответы",
        "greeting": "Привет! Я ваш голосовой ассистент. Чем могу помочь?",
        "wx_fail": "Не удалось получить погоду",
        "export_title": "Экспорт диалога",
        "export_filter": "Текст (*.txt)",
        "you": "Вы",
        "assistant": "Ассистент",
        "s_lang": "Язык",
        "s_city": "Город для погоды",
        "s_wake": "Слово активации",
        "s_model": "Модель Ollama",
        "s_mode": "Режим",
        "s_tts": "Озвучивать ответы",
        "save": "Сохранить",
        "cancel": "Отмена",
        "st_loading": "Загрузка моделей…",
        "st_idle": "Ожидание",
        "st_wake": "Слушаю слово «{}»…",
        "st_cmd": "Слушаю команду…",
        "st_think": "Думаю…",
        "st_speak": "Говорю…",
        "err_stopped": "Ассистент остановлен: {}",
        "err_voice": "Ошибка голосового ввода: {}",
        "err_answer": "Не удалось получить ответ: {}",
        "err_tts": "Ошибка озвучивания: {}",
        "err_generic": "{}",
    },
    "en": {
        "title": "Voice Assistant",
        "brand": "ASSISTANT",
        "online": "Online",
        "loading": "Loading",
        "settings": "Settings",
        "refresh": "Refresh",
        "system": "System",
        "weather": "Weather",
        "camera": "Camera",
        "cam_toggle": "Turn camera on / off",
        "cam_off": "Camera is off",
        "cam_missing": "QtMultimedia module is unavailable.",
        "cam_none": "No camera found.",
        "cam_error": "Camera error.",
        "uptime": "Uptime",
        "cpu_name": "Processor",
        "mem_name": "Memory",
        "load": "Load",
        "tile_cpu": "CPU",
        "tile_ram": "RAM",
        "tile_disk": "Disk",
        "tile_hum": "Humidity",
        "tile_wind": "Wind",
        "tile_feels": "Feels like",
        "tile_msgs": "Messages",
        "tile_lat": "Latency",
        "gb": "GB",
        "sec": "s",
        "ms": "m/s",
        "load_low": "Low",
        "load_mid": "Medium",
        "load_high": "High",
        "chat": "Chat",
        "clear": "Clear",
        "export": "Export",
        "placeholder": "Type a message…",
        "send": "Send",
        "mic_tip": "Listen for wake word",
        "tts_tip": "Speak replies",
        "greeting": "Hi! I'm your voice assistant. How can I help?",
        "wx_fail": "Could not get weather",
        "export_title": "Export chat",
        "export_filter": "Text (*.txt)",
        "you": "You",
        "assistant": "Assistant",
        "s_lang": "Language",
        "s_city": "Weather city",
        "s_wake": "Wake word",
        "s_model": "Ollama model",
        "s_mode": "Mode",
        "s_tts": "Speak replies",
        "save": "Save",
        "cancel": "Cancel",
        "st_loading": "Loading models…",
        "st_idle": "Idle",
        "st_wake": "Listening for “{}”…",
        "st_cmd": "Listening for command…",
        "st_think": "Thinking…",
        "st_speak": "Speaking…",
        "err_stopped": "Assistant stopped: {}",
        "err_voice": "Voice input error: {}",
        "err_answer": "Could not get a reply: {}",
        "err_tts": "Speech output error: {}",
        "err_generic": "{}",
    },
}

WMO = {
    "ru": {
        0: "ясно", 1: "малооблачно", 2: "переменная облачность", 3: "пасмурно",
        45: "туман", 48: "изморозь", 51: "морось", 53: "морось", 55: "сильная морось",
        56: "ледяная морось", 57: "ледяная морось", 61: "дождь", 63: "дождь",
        65: "сильный дождь", 66: "ледяной дождь", 67: "ледяной дождь", 71: "снег",
        73: "снег", 75: "сильный снег", 77: "снежные зёрна", 80: "ливни", 81: "ливни",
        82: "сильные ливни", 85: "снегопад", 86: "сильный снегопад", 95: "гроза",
        96: "гроза с градом", 99: "гроза с градом",
    },
    "en": {
        0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
        45: "fog", 48: "rime fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
        56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain",
        65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow",
        73: "snow", 75: "heavy snow", 77: "snow grains", 80: "showers", 81: "showers",
        82: "violent showers", 85: "snow showers", 86: "heavy snow showers",
        95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
    },
}

_lang = "ru"


def set_lang(code: str) -> None:
    global _lang
    if code in STR:
        _lang = code


def get_lang() -> str:
    return _lang


def tr(key: str, *args) -> str:
    s = STR[_lang].get(key) or STR["ru"].get(key, key)
    return s.format(*args) if args else s


def wmo(code: int) -> str:
    return WMO[_lang].get(code, "")
