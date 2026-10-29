from dataclasses import dataclass
from enum import StrEnum
from typing import Union, Optional
from datetime import datetime

import psutil


class TasksTypes(StrEnum):
  VOICE_RECORD = "voice_record"
  SPEACK = "speak"


@dataclass(frozen=True) 
class Task: 
    task_id: str
    task_os_sys_id: int  
    task_type: TasksTypes  
    mem_size: float 
    cpu_size: Union[int, float]   
    active: bool 
    is_delayed: bool = False
    run_at: Optional[datetime] | None 

    def get_os_sys_id(self) -> Optional[psutil.Process]: 
       try: 
        pr = psutil.Process(self.task_os_sys_id) 
        if pr.is_running(): 
           return pr 
       except (psutil.NoSuchProcess, psutil.AccessDenied) | Exception as e: 
          return None 
      