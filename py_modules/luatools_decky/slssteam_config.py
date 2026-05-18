from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .logger import logger
from .linux_platform import get_slssteam_config_path, get_slssteam_config_dir


def _read_yaml(path: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if not os.path.isfile(path):
        return data
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" not in line:
                    continue
                key, _, raw_value = line.partition(":")
                key = key.strip()
                raw_value = raw_value.strip()
                if raw_value.lower() in ("yes", "true"):
                    data[key] = True
                elif raw_value.lower() in ("no", "false"):
                    data[key] = False
                else:
                    try:
                        data[key] = int(raw_value)
                    except ValueError:
                        data[key] = raw_value
    except Exception as exc:
        logger.warn(f"SLSsteam: failed to read config at {path}: {exc}")
    return data


def _write_yaml(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {'yes' if value else 'no'}")
        else:
            lines.append(f"{key}: {value}")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except Exception as exc:
        logger.warn(f"SLSsteam: failed to write config at {path}: {exc}")


def read_config() -> Dict[str, Any]:
    return _read_yaml(get_slssteam_config_path())

def write_config(data: Dict[str, Any]) -> None:
    _write_yaml(get_slssteam_config_path(), data)

def get_value(key: str, default: Any = None) -> Any:
    return read_config().get(key, default)

def set_value(key: str, value: Any) -> None:
    cfg = read_config()
    cfg[key] = value
    write_config(cfg)

def is_play_not_owned_enabled() -> bool:
    return bool(get_value("PlayNotOwnedGames", False))

def set_play_not_owned(enabled: bool) -> None:
    set_value("PlayNotOwnedGames", enabled)

def is_safe_mode_enabled() -> bool:
    return bool(get_value("SafeMode", False))

def set_safe_mode(enabled: bool) -> None:
    set_value("SafeMode", enabled)

def config_exists() -> bool:
    return os.path.isfile(get_slssteam_config_path())

def get_sls_version() -> Optional[str]:
    return get_value("Version", None)
