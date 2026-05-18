from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from ..logger import logger
from ..paths import get_plugin_dir
from .options import (
    SETTINGS_GROUPS,
    get_default_settings_values,
    get_settings_schema,
    merge_defaults_with_values,
)

_SETTINGS_FILE = "settings.json"
_SETTINGS_CACHE: Optional[Dict[str, Any]] = None


def _get_settings_path() -> str:
    try:
        import decky
        return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, _SETTINGS_FILE)
    except Exception:
        return os.path.join(get_plugin_dir(), _SETTINGS_FILE)


def _load_settings() -> Dict[str, Any]:
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is not None:
        return _SETTINGS_CACHE
    path = _get_settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                _SETTINGS_CACHE = json.load(f)
        except Exception as exc:
            logger.warn(f"Failed to load settings: {exc}")
            _SETTINGS_CACHE = {}
    else:
        _SETTINGS_CACHE = {}
    return _SETTINGS_CACHE


def _save_settings(settings: Dict[str, Any]) -> bool:
    global _SETTINGS_CACHE
    path = _get_settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        _SETTINGS_CACHE = settings
        return True
    except Exception as exc:
        logger.warn(f"Failed to save settings: {exc}")
        return False


def get_setting(key: str, default: Any = None) -> Any:
    settings = _load_settings()
    return settings.get(key, default)


def set_setting(key: str, value: Any) -> bool:
    settings = _load_settings()
    settings[key] = value
    return _save_settings(settings)


def _load_morrenus_key_from_user_apis() -> str:
    try:
        from ..downloads import load_user_apis
        data = load_user_apis()
        for api in data.get("api_list", []):
            url = api.get("url", "")
            m = __import__("re").search(r"api_key=([^&\s]+)", url)
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""

def get_settings_payload() -> Dict[str, Any]:
    settings = _load_settings()
    merged = merge_defaults_with_values(settings)
    schema = get_settings_schema()

    morrenus_key = _load_morrenus_key_from_user_apis()
    if morrenus_key:
        merged["morrenusKey"] = morrenus_key

    available_locales = get_available_locales()
    available_themes = _get_available_themes()

    payload = {
        "version": 1,
        "schema": schema,
        "values": merged,
        "language": merged.get("language", "en"),
        "locales": available_locales,
        "translations": get_translation_map(merged.get("language", "en")),
    }
    return payload


def _save_morrenus_key_to_user_apis(key_value: str) -> bool:
    try:
        from ..downloads import update_morrenus_key
        result = update_morrenus_key(key_value)
        data = json.loads(result)
        return data.get("success", False)
    except Exception as exc:
        logger.warn(f"Failed to save Morrenus key from settings: {exc}")
        return False

def apply_settings_changes(changes: Dict[str, Any]) -> Dict[str, Any]:
    try:
        settings = _load_settings()
        schema_keys = set()
        for group in SETTINGS_GROUPS:
            for opt in group.options:
                schema_keys.add(opt.key)

        morrenus_value = None
        for key, value in changes.items():
            if key == "morrenusKey":
                morrenus_value = value
            elif key in schema_keys:
                settings[key] = value

        if morrenus_value is not None:
            _save_morrenus_key_to_user_apis(morrenus_value)

        if _save_settings(settings):
            return {"success": True}
        return {"success": False, "error": "Failed to save settings"}
    except Exception as exc:
        logger.warn(f"ApplySettingsChanges failed: {exc}")
        return {"success": False, "error": str(exc)}


def get_available_locales() -> List[Dict[str, str]]:
    locales_dir = _get_locales_dir()
    available = []
    if os.path.exists(locales_dir):
        for fname in sorted(os.listdir(locales_dir)):
            if fname.endswith(".json"):
                lang = fname.replace(".json", "")
                available.append({"value": lang, "label": lang})
    if not available:
        available.append({"value": "en", "label": "English"})
    return available


def get_translation_map(language: str = "en") -> Dict[str, str]:
    locale_file = os.path.join(_get_locales_dir(), f"{language}.json")
    if os.path.exists(locale_file):
        try:
            with open(locale_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _get_locales_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "locales")


def _get_available_themes() -> List[Dict[str, str]]:
    from ..paths import get_plugin_dir
    themes_path = os.path.join(get_plugin_dir(), "public", "themes", "themes.json")
    if os.path.exists(themes_path):
        try:
            with open(themes_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return [{"id": "original", "name": "Original"}]
