"""JSON configuration loading and creation."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigurationError

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class AppConfig:
    database_path: Path
    log_level: str = "INFO"


def default_config_path() -> Path:
    return Path.home() / ".expense_manager" / "config.json"


def load_config(path: Path) -> AppConfig:
    config_path = path.expanduser()
    defaults = AppConfig(database_path=config_path.parent / "expenses.sqlite3")
    if not config_path.exists():
        return defaults

    try:
        raw: Any = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read configuration file '{config_path}': {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError("Configuration must be a JSON object.")

    unknown_keys = set(raw) - {"database_path", "log_level"}
    if unknown_keys:
        keys = ", ".join(sorted(str(key) for key in unknown_keys))
        raise ConfigurationError(f"Unknown configuration option(s): {keys}.")

    database_value = raw.get("database_path", str(defaults.database_path))
    if not isinstance(database_value, str) or not database_value.strip():
        raise ConfigurationError("'database_path' must be a non-empty string.")
    database_path = Path(database_value).expanduser()
    if not database_path.is_absolute():
        database_path = config_path.parent / database_path

    log_level = raw.get("log_level", "INFO")
    if not isinstance(log_level, str) or log_level.upper() not in VALID_LOG_LEVELS:
        choices = ", ".join(sorted(VALID_LOG_LEVELS))
        raise ConfigurationError(f"'log_level' must be one of: {choices}.")

    return AppConfig(database_path=database_path, log_level=log_level.upper())


def write_default_config(path: Path, force: bool = False) -> None:
    config_path = path.expanduser()
    if config_path.exists() and not force:
        raise ConfigurationError(
            f"Configuration file '{config_path}' already exists; use --force to replace it."
        )

    config = {
        "database_path": "expenses.sqlite3",
        "log_level": "INFO",
    }
    temporary_path = config_path.with_name(f"{config_path.name}.tmp")
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_path, config_path)
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ConfigurationError(f"Cannot write configuration file '{config_path}': {exc}") from exc
