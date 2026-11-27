
import asyncio
import os
import time

from PyQt5.QtCore import QThread, pyqtSignal


class Worker(QThread):
    state = pyqtSignal(str, str)      
    message = pyqtSignal(str, str)    
    error = pyqtSignal(str, str)     
    latency = pyqtSignal(float)
    ready = pyqtSignal()
    loading = pyqtSignal()           
    listening_changed = pyqtSignal(bool)

    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self.cfg = dict(cfg)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue | None = None
        self._lock: asyncio.Lock | None = None
        self._listen_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._engine_lang: str | None = None
        self.engine = None

    def submit(self, *cmd) -> None:
        loop, queue = self._loop, self._queue
        if loop and queue:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, cmd)
            except RuntimeError:  
                pass

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:  # noqa: BLE001
            self.error.emit("err_stopped", str(exc))
        finally:
            self._shutdown_loop()

    def _shutdown_loop(self) -> None:
        loop = self._loop
        try:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        finally:
            loop.close()
            self._loop = None

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _load_engine(self) -> None:
        self.state.emit("idle", "st_idle")
        self._engine_lang = self.cfg.get("lang")
        self.engine = None

    async def _process(self, request: str) -> None:
        request = request.strip()
        if not request:
            return
        self.message.emit("user", request)
        self.state.emit("thinking", "st_think")
        started = time.perf_counter()
        try:
            import httpx

            url = self.cfg.get("api_url", "http://127.0.0.1:8765")
            key = self.cfg.get("api_key") or os.environ.get("ASSISTANT_API_KEY") or "dev-key"
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{url.rstrip('/')}/v1/requests",
                    json={"request": request},
                    headers={"Authorization": f"Bearer {key}"},
                )
                r.raise_for_status()
                response = r.json().get("response", "")
        except Exception as exc:  # noqa: BLE001
            self.error.emit("err_answer", str(exc))
            self._back_to_idle()
            return
        self.latency.emit(time.perf_counter() - started)
        self.message.emit("assistant", response)
        self._back_to_idle()

    def _back_to_idle(self) -> None:
        self.state.emit("idle", "st_idle")

    async def _main(self) -> None:
        self._queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        await self._load_engine()
        self.ready.emit()
        try:
            while True:
                cmd = await self._queue.get()
                kind = cmd[0]
                if kind == "stop":
                    break
                if kind == "text":
                    self._spawn(self._process(cmd[1]))
                elif kind == "listen":
                    self._set_listening(cmd[1])
                elif kind == "cfg":
                    await self._apply_cfg(cmd[1])
        finally:
            self._set_listening(False)
            if self.engine is not None:
                await self.engine.stop()

    async def _apply_cfg(self, new: dict) -> None:
        old = dict(self.cfg)
        self.cfg.update(new)
        if self.cfg["lang"] != self._engine_lang:
            await self._reload_engine()
            return
        try:
            if self.cfg["mode"] != old.get("mode"):
                self.engine.select_mode(self.cfg["mode"])
            if self.cfg["model"] != old.get("model") and hasattr(self.engine.llm_engine, "model"):
                self.engine.llm_engine.model = self.cfg["model"]
        except Exception as exc:  # noqa: BLE001
            self.error.emit("err_generic", str(exc))

    async def _reload_engine(self) -> None:
        self.loading.emit()
        self._set_listening(False)
        try:
            await self.engine.stop()
        except Exception as exc:  # noqa: BLE001
            self.error.emit("err_generic", str(exc))
        try:
            await self._load_engine()
        except Exception as exc:  # noqa: BLE001
            self.error.emit("err_stopped", str(exc))
            raise
        self.ready.emit()

    def _set_listening(self, on: bool) -> None:
        self.listening_changed.emit(on)
        return

    async def _voice_loop(self) -> None:
        try:
            while True:
                self.state.emit("listening", "st_wake")
                if not await self.engine.wake_up.recognize_wake_up_word(self.cfg["wake"]):
                    break
                self.state.emit("listening", "st_cmd")
                request = await self.engine.voice_r.start_recognize()
                if request:
                    await self._process(request)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.error.emit("err_voice", str(exc))
        finally:
            if self._listen_task is asyncio.current_task():
                self._listen_task = None
                self.listening_changed.emit(False)
                self.state.emit("idle", "st_idle")

    async def _process(self, request: str) -> None:
        request = request.strip()
        if not request:
            return
        self.message.emit("user", request)
        async with self._lock:  
            self.state.emit("thinking", "st_think")
            started = time.perf_counter()
            try:
                import httpx

                url = self.cfg.get("api_url", "http://127.0.0.1:8765")
                key = self.cfg.get("api_key") or os.environ.get("ASSISTANT_API_KEY") or "dev-key"
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(
                        f"{url.rstrip('/')}/v1/requests",
                        json={"request": request},
                        headers={"Authorization": f"Bearer {key}"},
                    )
                    r.raise_for_status()
                    response = r.json().get("response", "")
            except Exception as exc:  # noqa: BLE001
                self.error.emit("err_answer", str(exc))
                self._back_to_idle()
                return
            self.latency.emit(time.perf_counter() - started)
            self.message.emit("assistant", response)
            self._spawn(self._save(request, response))  
            if self.cfg.get("tts", True) and response:
                self.state.emit("speaking", "st_speak")
                try:
                    await self.engine.voice_tts.say(response)
                except Exception as exc:  # noqa: BLE001
                    self.error.emit("err_tts", str(exc))
            self._back_to_idle()

    async def _save(self, request: str, response: str) -> None:
        try:
            await self.engine.db.save_chat_message(text=request, role="user")
            await self.engine.db.save_chat_message(text=response, role="assistant")
        except Exception:  # noqa: BLE001
            pass

    def _back_to_idle(self) -> None:
        if self._listen_task:
            self.state.emit("listening", "st_wake")
        else:
            self.state.emit("idle", "st_idle")
