"""Centralized, project-relative storage for JSON and YAML configuration files."""

import json
import os
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path(__file__).resolve().parent / "cfgs"
cfg_file_path = str(CONFIG_DIR / "main_cfg.json")


class ConfigStore:
	"""Load and save project configs without depending on the working directory.

	Config names are relative to ``core/cfgs``. JSON and YAML files are supported;
	missing files can be initialized from the supplied defaults.
	"""

	def __init__(self, root: str | Path = CONFIG_DIR) -> None:
		self.root = Path(root).resolve()

	def path(self, name: str | Path) -> Path:
		"""Resolve a config name under this store's root, preventing path traversal."""
		candidate = Path(name)
		if candidate.is_absolute():
			resolved = candidate.resolve()
		else:
			resolved = (self.root / candidate).resolve()
			if not resolved.is_relative_to(self.root):
				raise ValueError("Config names must stay inside the config directory")

		if resolved.suffix.casefold() not in {".json", ".yaml", ".yml"}:
			raise ValueError("Config files must use .json, .yaml, or .yml")
		return resolved

	def load(
		self,
		name: str | Path,
		defaults: Mapping[str, Any] | None = None,
		*,
		create: bool = True,
	) -> dict[str, Any]:
		"""Read a config, optionally creating a missing file from defaults."""
		path = self.path(name)
		if not path.exists():
			data = dict(defaults or {})
			if create:
				self.save_path(path, data)
			return data
		return self.load_path(path)

	@staticmethod
	def load_path(
		path: str | Path,
		defaults: Mapping[str, Any] | None = None,
		*,
		create: bool = False,
	) -> dict[str, Any]:
		"""Load a JSON/YAML config from a specific path."""
		config_path = Path(path)
		if not config_path.exists():
			data = dict(defaults or {})
			if create:
				ConfigStore.save_path(config_path, data)
			return data

		with config_path.open("r", encoding="utf-8") as config_file:
			if config_path.suffix.casefold() == ".json":
				data = json.load(config_file)
			elif config_path.suffix.casefold() in {".yaml", ".yml"}:
				data = yaml.safe_load(config_file)
			else:
				raise ValueError(f"Unsupported config format: {config_path}")

		if data is None:
			return dict(defaults or {})
		if not isinstance(data, dict):
			raise ValueError(f"Config must contain a mapping: {config_path}")
		return data

	def save(self, name: str | Path, data: Mapping[str, Any]) -> Path:
		"""Save a config atomically and return its resolved path."""
		path = self.path(name)
		self.save_path(path, data)
		return path

	@staticmethod
	def save_path(path: str | Path, data: Mapping[str, Any]) -> None:
		"""Write a mapping as JSON or YAML using an atomic file replacement."""
		config_path = Path(path)
		suffix = config_path.suffix.casefold()
		if suffix not in {".json", ".yaml", ".yml"}:
			raise ValueError(f"Unsupported config format: {config_path}")

		config_path.parent.mkdir(parents=True, exist_ok=True)
		serialized = (
			json.dumps(data, ensure_ascii=False, indent=2) + "\n"
			if suffix == ".json"
			else yaml.safe_dump(
				deepcopy(dict(data)),
				allow_unicode=True,
				sort_keys=False,
				default_flow_style=False,
			)
		)

		temporary_path: str | None = None
		try:
			with tempfile.NamedTemporaryFile(
				"w",
				encoding="utf-8",
				dir=config_path.parent,
				delete=False,
				suffix=".tmp",
			) as config_file:
				temporary_path = config_file.name
				config_file.write(serialized)
			os.replace(temporary_path, config_path)
		finally:
			if temporary_path and os.path.exists(temporary_path):
				os.unlink(temporary_path)