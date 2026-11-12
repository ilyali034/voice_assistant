"""Start Ollama and pull the model when the backend manages a local instance."""

import atexit
import os
import shutil
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
_process: subprocess.Popen | None = None


def _log(message: str) -> None:
    print(f"[ollama] {message}", flush=True)


def is_local(base_url: str) -> bool:
    return (urlparse(base_url).hostname or "") in _LOCAL_HOSTS


def is_up(base_url: str) -> bool:
    try:
        with urlopen(f"{base_url}/api/tags", timeout=1) as response:
            return response.status == 200
    except (URLError, OSError, ValueError):
        return False


def find_ollama() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
    ]
    return next((path for path in candidates if path and os.path.isfile(path)), None)


def _start_server(exe: str, base_url: str, timeout: float = 40.0) -> None:
    global _process
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    _log("запускаю ollama serve")
    _process = subprocess.Popen(
        [exe, "serve"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    atexit.register(stop)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _process.poll() is not None:
            raise RuntimeError("Процесс ollama serve завершился сразу после запуска")
        if is_up(base_url):
            return
        time.sleep(0.5)
    raise RuntimeError(f"Ollama не ответила на {base_url} за {timeout:.0f} с")


def _model_installed(exe: str, model: str) -> bool:
    result = subprocess.run(
        [exe, "list"], capture_output=True, text=True, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
    )
    if result.returncode != 0:
        return False
    names = [line.split()[0] for line in result.stdout.splitlines()[1:] if line.split()]
    return any(model == name or name.startswith(f"{model}:") for name in names)


def ensure_ollama(base_url: str, model: str) -> None:
    """Make sure a local Ollama serves ``model``. Remote URLs are left alone."""
    base_url = base_url.rstrip("/")
    if not is_local(base_url):
        _log("удалённый Ollama, автозапуск пропущен")
        return
    exe = find_ollama()
    if exe is None:
        raise RuntimeError("Ollama не найдена. Установите её с https://ollama.com/download")
    if is_up(base_url):
        _log("уже запущена")
    else:
        _start_server(exe, base_url)
    if _model_installed(exe, model):
        _log(f"модель {model} готова")
        return
    _log(f"скачиваю модель {model} (первый запуск, может занять несколько минут)")
    pull = subprocess.run([exe, "pull", model], check=False)
    if pull.returncode != 0:
        raise RuntimeError(f"Не удалось скачать модель {model}")
    _log(f"модель {model} готова")


def stop() -> None:
    """Stop only an Ollama process that this backend started."""
    global _process
    process, _process = _process, None
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=10)
    except (subprocess.TimeoutExpired, OSError):
        process.kill()
