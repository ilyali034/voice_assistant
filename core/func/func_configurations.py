from dataclasses import asdict, dataclass

from ..cfg import ConfigStore


@dataclass
class FuncCfg:
    lang: str = "ru"
    llm: bool = True


def make_start_cfg(cfg: FuncCfg) -> None:
    """Persist startup preferences in the project's main JSON config."""
    ConfigStore().save("main_cfg.json", asdict(cfg))


def load_start_cfg() -> FuncCfg:
    """Load startup preferences, creating the default config when missing."""
    defaults = asdict(FuncCfg())
    data = ConfigStore().load("main_cfg.json", defaults)
    return FuncCfg(**data)