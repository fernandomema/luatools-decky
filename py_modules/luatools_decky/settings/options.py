from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SettingOption:
    key: str
    label: str
    option_type: str
    default: Any
    description: str = ""
    choices: Optional[List[Dict[str, Any]]] = None
    requires_restart: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SettingGroup:
    key: str
    label: str
    description: str
    options: List[SettingOption]


SETTINGS_GROUPS: List[SettingGroup] = [
    SettingGroup(
        key="general",
        label="General",
        description="Global LuaTools preferences.",
        options=[
            SettingOption(
                key="language",
                label="Language",
                option_type="select",
                description="Choose the language used by LuaTools.",
                default="en",
                metadata={"dynamicChoices": "locales"},
            ),
            SettingOption(
                key="theme",
                label="Theme",
                option_type="select",
                description="Choose the color theme for LuaTools interface.",
                default="original",
                metadata={"dynamicChoices": "themes"},
            ),
            SettingOption(
                key="donateKeys",
                label="Donate Steam Decryption Keys",
                option_type="boolean",
                description="When enabled, your downloaded AppTokens will be submitted to help build a shared database.",
                default=False,
            ),
        ],
    ),
    SettingGroup(
        key="downloads",
        label="Downloads",
        description="Game manifest download settings.",
        options=[
            SettingOption(
                key="autoExtract",
                label="Auto-extract manifests",
                option_type="boolean",
                description="Automatically extract .manifest files to depotcache on download.",
                default=True,
            ),
            SettingOption(
                key="saveLuaScripts",
                label="Save Lua scripts",
                option_type="boolean",
                description="Save .lua files to stplug-in directory after download.",
                default=True,
            ),
            SettingOption(
                key="morrenusKey",
                label="Morrenus API Key",
                option_type="text",
                description="Your Morrenus API key for manifest downloads.",
                default="",
            ),
            SettingOption(
                key="launcherPath",
                label="Launcher Executable Path",
                option_type="text",
                description="Path to ACCELA/Bifrost launcher executable.",
                default="",
            ),
        ],
    ),
]


def get_settings_schema() -> List[Dict[str, Any]]:
    schema = []
    for group in SETTINGS_GROUPS:
        group_schema = {
            "key": group.key,
            "label": group.label,
            "description": group.description,
            "options": [],
        }
        for opt in group.options:
            opt_schema = {
                "key": opt.key,
                "label": opt.label,
                "option_type": opt.option_type,
                "default": opt.default,
                "description": opt.description,
                "requires_restart": opt.requires_restart,
            }
            if opt.choices:
                opt_schema["choices"] = opt.choices
            if opt.metadata:
                opt_schema["metadata"] = opt.metadata
            group_schema["options"].append(opt_schema)
        schema.append(group_schema)
    return schema


def get_default_settings_values() -> Dict[str, Any]:
    values = {}
    for group in SETTINGS_GROUPS:
        for opt in group.options:
            values[opt.key] = opt.default
    return values


def merge_defaults_with_values(values: Dict[str, Any]) -> Dict[str, Any]:
    merged = get_default_settings_values()
    merged.update(values)
    return merged
