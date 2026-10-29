from dataclasses import asdict, dataclass
import json 

from cfg import cfg_file_path 

@dataclass
class FuncCfg(): 
    lang: str 
    llm: bool 

def make_start_cfg(cfg: FuncCfg): 
    with open(cfg_file_path, 'w', encoding="utf-8") as cfg_file: 
        json.dump(asdict(cfg), cfg_file, ensure_ascii=False, indent=4)