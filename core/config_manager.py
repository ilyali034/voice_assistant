"""Composable loading for the assistant's modular YAML configuration."""

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from .cfg import CONFIG_DIR, ConfigStore


class AssistantConfigLoader:
    """Load built-in config modules and user overrides in a stable order.

    Files under ``assistant/`` are the built-in modules. The legacy
    ``assistant.yaml`` file remains an optional compatibility overlay, and
    ``assistant.d/*.yaml`` files are user overrides loaded alphabetically.
    Nested mappings are merged; other values are replaced by later files.
    """

    def __init__(self, config_dir: str | Path = CONFIG_DIR) -> None:
        self.config_dir = Path(config_dir).resolve()

    def load(self) -> dict[str, Any]:
        """Load and merge all available assistant configuration layers."""
        result: dict[str, Any] = {}
        module_dir = self.config_dir / "assistant"
        for path in self._yaml_files(module_dir):
            result = self._merge(result, ConfigStore.load_path(path))

        legacy_path = self.config_dir / "assistant.yaml"
        if legacy_path.is_file():
            result = self._merge(result, ConfigStore.load_path(legacy_path))

        overrides_dir = self.config_dir / "assistant.d"
        for path in self._yaml_files(overrides_dir):
            result = self._merge(result, ConfigStore.load_path(path))
        return result

    @staticmethod
    def _yaml_files(directory: Path) -> list[Path]:
        if not directory.is_dir():
            return []
        return sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.casefold() in {".yaml", ".yml"}
            ),
            key=lambda path: path.name.casefold(),
        )

    @classmethod
    def _merge(
        cls,
        base: Mapping[str, Any],
        overlay: Mapping[str, Any],
    ) -> dict[str, Any]:
        merged = deepcopy(dict(base))
        for key, value in overlay.items():
            previous = merged.get(key)
            if isinstance(previous, Mapping) and isinstance(value, Mapping):
                merged[key] = cls._merge(previous, value)
            else:
                merged[key] = deepcopy(value)
        return merged


def load_assistant_config(config_dir: str | Path = CONFIG_DIR) -> dict[str, Any]:
    """Convenience function for loading the default assistant config tree."""
    return AssistantConfigLoader(config_dir).load()


def get_search_engine() -> str:
    """Return the configured web search engine, defaulting to Google."""
    if CONFIG_DIR is None: 
        raise Exception("Config is not defined")
    web_config = load_assistant_config(CONFIG_DIR).get("web", {})
    if not isinstance(web_config, Mapping):
        return "google"
    return str(web_config.get("search_engine", "google")).casefold()
