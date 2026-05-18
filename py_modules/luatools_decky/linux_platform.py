from __future__ import annotations

import os
import subprocess
from typing import Optional

_STEAM_PATHS = [
    os.path.expanduser("~/.steam/steam"),
    os.path.expanduser("~/.local/share/Steam"),
    "/opt/steam/steam",
    "/usr/local/steam",
]

def find_steam_root() -> Optional[str]:
    for path in _STEAM_PATHS:
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "steam.sh")):
            return path
    for path in _STEAM_PATHS:
        if os.path.isdir(path):
            return path
    return None

def get_stplugin_dir(steam_root: Optional[str] = None) -> Optional[str]:
    root = steam_root or find_steam_root()
    if root is None:
        return None
    return os.path.join(root, "config", "stplug-in")

def get_depotcache_dir(steam_root: Optional[str] = None) -> Optional[str]:
    root = steam_root or find_steam_root()
    if root is None:
        return None
    return os.path.join(root, "depotcache")

_SLSSTEAM_CANDIDATES = [
    os.path.expanduser("~/.local/share/SLSsteam"),
    os.path.expanduser("~/SLSsteam"),
    "/opt/SLSsteam",
]

def get_slssteam_install_dir() -> str:
    for path in _SLSSTEAM_CANDIDATES:
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "SLSsteam.so")):
            return path
    return os.path.expanduser("~/.local/share/SLSsteam")

def get_slssteam_config_dir() -> str:
    return os.path.expanduser("~/.config/SLSsteam")

def get_slssteam_config_path() -> str:
    return os.path.join(get_slssteam_config_dir(), "config.yaml")

def check_slssteam_installed() -> bool:
    for path in _SLSSTEAM_CANDIDATES:
        so_path = os.path.join(path, "SLSsteam.so")
        if os.path.isfile(so_path):
            return True
    return False

_ACCELA_CANDIDATES = [
    os.path.expanduser("~/.local/share/ACCELA"),
    os.path.expanduser("~/accela"),
]

def get_accela_dir() -> Optional[str]:
    for path in _ACCELA_CANDIDATES:
        if os.path.isdir(path):
            return path
    return None

def check_accela_installed() -> bool:
    return get_accela_dir() is not None

def get_accela_run_script() -> Optional[str]:
    accela_dir = get_accela_dir()
    if not accela_dir:
        return None
    for name in ("launch_debug.sh", "run.sh"):
        script = os.path.join(accela_dir, name)
        if os.path.isfile(script):
            return script
    return None

def open_directory(path: str) -> None:
    subprocess.Popen(
        ["xdg-open", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def _get_ld_audit_line() -> str:
    sls_dir = get_slssteam_install_dir()
    return f'export LD_AUDIT={sls_dir}/library-inject.so:{sls_dir}/SLSsteam.so'

def verify_slssteam_injected() -> dict:
    if not check_slssteam_installed():
        return {"patched": False, "already_ok": False, "error": "SLSsteam not installed"}
    steam_sh = None
    for candidate in _STEAM_PATHS:
        path = os.path.join(candidate, "steam.sh")
        if os.path.isfile(path):
            steam_sh = path
            break
    if not steam_sh:
        return {"patched": False, "already_ok": False, "error": "steam.sh not found"}
    try:
        with open(steam_sh, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:
        return {"patched": False, "already_ok": False, "error": f"read failed: {exc}"}
    if "LD_AUDIT" in content and "SLSsteam" in content:
        return {"patched": False, "already_ok": True, "error": None}
    try:
        ld_audit_line = _get_ld_audit_line()
        lines = content.splitlines(keepends=True)
        insert_pos = min(9, len(lines))
        lines.insert(insert_pos, ld_audit_line + "\n")
        with open(steam_sh, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return {"patched": True, "already_ok": False, "error": None}
    except Exception as exc:
        return {"patched": False, "already_ok": False, "error": f"write failed: {exc}"}

def get_platform_summary() -> dict:
    summary = {
        "steam_root": find_steam_root(),
        "slssteam_installed": check_slssteam_installed(),
        "accela_installed": check_accela_installed(),
        "accela_dir": get_accela_dir(),
    }
    if summary["slssteam_installed"]:
        inj = verify_slssteam_injected()
        summary["slssteam_injection"] = inj
    return summary
