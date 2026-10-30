import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional
import psutil
from .tasks import Task, TasksTypes

class LowLevelTaskManager:
    """
    Asynchronous low-level task scheduler and process resource monitor.
    Tracks OS process lifecycles and safely fires delayed voice and speech tasks.
    """
    def __init__(self):
        self.active_tasks: Dict[str, Task] = {}
        self._loop_task: Optional[asyncio.Task] = None
        self.is_running = False

    def register_task(self, task: Task):
        """
        Registers a new operational payload tracking configuration in the supervisor matrix.
        """
        self.active_tasks[task.task_id] = task
        print(f"[TaskManager] Registered execution pipeline task: {task.task_id} ({task.task_type})")

    async def start(self):
        """
        Spawns the long-running daemonized continuous asynchronous observation matrix loop.
        """
        self.is_running = True
        self._loop_task = asyncio.create_task(self._main_loop())
        print("[TaskManager] Low-level operational process tracking engine operational.")

    async def stop(self):
        """
        Gracefully signals and tears down active background scheduling contexts.
        """
        self.is_running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        print("[TaskManager] Process engine supervisor safely halted.")

    async def _main_loop(self):
        """
        Continuous observation lifecycle loop parsing resources and delta tracking.
        """
        while self.is_running:
            try:
                now = datetime.now(timezone.utc)
                
                for task_id in list(self.active_tasks.keys()):
                    task = self.active_tasks[task_id]
                    
                    process: Optional[psutil.Process] = task.get_os_sys_id()
                    if process is None and not task.is_delayed:
                        print(f"[TaskManager] Subprocess execution complete or unallocated context for: {task_id}. Purging record.")
                        self.active_tasks.pop(task_id, None)
                        continue

                    if task.is_delayed and task.run_at:
                        run_at_utc = task.run_at.replace(tzinfo=timezone.utc) if task.run_at.tzinfo is None else task.run_at
                        
                        if now >= run_at_utc:
                            print(f"[TaskManager] Scheduled execution boundary reached for task: {task_id}!")
                            await self._execute_delayed_task(task)

                await asyncio.sleep(2)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[TaskManager] Processing failure experienced in active verification loop: {e}")

    async def _execute_delayed_task(self, task: Task):
        """
        Executes non-blocking sub-tasks tailored around specific voice engine contexts.
        """
        if task.task_type == TasksTypes.VOICE_RECORD:
            print(f"[Worker] Activating hardware-level microphone recording stream context: {task.task_id}...")
            
        elif task.task_type == TasksTypes.SPEAK:
            print(f"[Worker] Initializing text-to-speech engine runtime wrapper payload: {task.task_id}...")

        self.active_tasks.pop(task.task_id, None)
