
from dataclasses import dataclass 

@dataclass
class QdrantCfg: 
    host: str 
    port: int 
    url: str | None 
    api_key: str | None 
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2" 
    local: bool 
    local_path: str | None 