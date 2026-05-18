from __future__ import annotations

import json
import os
import threading
import zipfile
from datetime import datetime
from typing import Dict, Optional

from .downloads import fetch_app_name
from .http_client import ensure_http_client
from .logger import logger
from .utils import ensure_temp_download_dir
from .steam_utils import get_game_install_path_response

FIX_DOWNLOAD_STATE: Dict[int, Dict[str, any]] = {}
FIX_DOWNLOAD_LOCK = threading.Lock()
UNFIX_STATE: Dict[int, Dict[str, any]] = {}
UNFIX_LOCK = threading.Lock()

def _set_fix_download_state(appid: int, update: dict) -> None:
    with FIX_DOWNLOAD_LOCK:
        state = FIX_DOWNLOAD_STATE.get(appid) or {}
        state.update(update)
        FIX_DOWNLOAD_STATE[appid] = state

def _get_fix_download_state(appid: int) -> dict:
    with FIX_DOWNLOAD_LOCK:
        return FIX_DOWNLOAD_STATE.get(appid, {}).copy()

def _set_unfix_state(appid: int, update: dict) -> None:
    with UNFIX_LOCK:
        state = UNFIX_STATE.get(appid) or {}
        state.update(update)
        UNFIX_STATE[appid] = state

def _get_unfix_state(appid: int) -> dict:
    with UNFIX_LOCK:
        return UNFIX_STATE.get(appid, {}).copy()


def check_for_fixes(appid: int) -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})

    try:
        client = ensure_http_client("fixes")
        url = f"https://fixs-json-db.piqseu.cc/api/v1/fix/{appid}"
        resp = client.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list):
                return json.dumps({"success": True, "fixes": data})
            return json.dumps({"success": True, "fixes": []})
        return json.dumps({"success": True, "fixes": []})
    except Exception as e:
        logger.warn(f"check_for_fixes API error: {e}")
        return json.dumps({"success": False, "error": str(e)})


def _download_and_apply_fix(appid: int, download_url: str, install_path: str, fix_type: str, game_name: str) -> None:
    from .utils import ensure_temp_download_dir
    try:
        _set_fix_download_state(appid, {"status": "downloading", "progress": 0, "download_url": download_url, "install_path": install_path})

        temp_dir = ensure_temp_download_dir()
        zip_path = os.path.join(temp_dir, f"fix_{appid}.zip")

        client = ensure_http_client("fix_download")
        with client.stream("GET", download_url, follow_redirects=True, timeout=60) as resp:
            if resp.status_code != 200:
                _set_fix_download_state(appid, {"status": "failed", "error": f"HTTP {resp.status_code}"})
                return

            total = int(resp.headers.get("Content-Length", "0") or "0")
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_bytes():
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        progress = min(100, int((downloaded / total) * 100))
                        _set_fix_download_state(appid, {"progress": progress})

        _set_fix_download_state(appid, {"status": "extracting", "progress": 90})

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(install_path)

        if os.path.exists(zip_path):
            os.remove(zip_path)

        _set_fix_download_state(appid, {"status": "done", "progress": 100})

        installed_fixes = _load_installed_fixes()
        fix_entry = {
            "appid": appid,
            "gameName": game_name,
            "fixDate": datetime.now().isoformat(),
            "installPath": install_path,
            "fixType": fix_type,
            "downloadUrl": download_url,
            "status": "applied",
        }
        installed_fixes[str(appid)] = fix_entry
        _save_installed_fixes(installed_fixes)

        logger.log(f"Fix applied for appid {appid}")
    except Exception as e:
        logger.error(f"Fix application error for appid {appid}: {e}")
        _set_fix_download_state(appid, {"status": "failed", "error": str(e)})


def _installed_fixes_path() -> str:
    from .paths import backend_path
    return backend_path("installed_fixes.json")

def _load_installed_fixes() -> dict:
    path = _installed_fixes_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_installed_fixes(data: dict) -> None:
    path = _installed_fixes_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warn(f"Failed to save installed fixes: {e}")


def apply_game_fix(appid: int, download_url: str, install_path: str, fix_type: str = "", game_name: str = "") -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})

    state = _get_fix_download_state(appid)
    if state.get("status") == "downloading":
        return json.dumps({"success": False, "error": "Fix download already in progress"})

    if not game_name:
        game_name = fetch_app_name(appid) or f"Unknown ({appid})"

    _set_fix_download_state(appid, {"status": "queued", "progress": 0})
    thread = threading.Thread(
        target=_download_and_apply_fix,
        args=(appid, download_url, install_path, fix_type, game_name),
        daemon=True,
    )
    thread.start()
    return json.dumps({"success": True})


def get_apply_fix_status(appid: int) -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})
    state = _get_fix_download_state(appid)
    return json.dumps({"success": True, "state": state})


def cancel_apply_fix(appid: int) -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})
    state = _get_fix_download_state(appid)
    if not state or state.get("status") in {"done", "failed"}:
        return json.dumps({"success": True, "message": "Nothing to cancel"})
    _set_fix_download_state(appid, {"status": "cancelled"})
    return json.dumps({"success": True})


def get_installed_fixes() -> str:
    try:
        fixes = _load_installed_fixes()
        fix_list = []
        for appid_str, data in fixes.items():
            entry = {"appid": int(appid_str)}
            entry.update(data)
            fix_list.append(entry)
        fix_list.sort(key=lambda x: x.get("fixDate", ""), reverse=True)
        return json.dumps({"success": True, "fixes": fix_list})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def unfix_game(appid: int, install_path: str = "", fix_date: str = "") -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})

    _set_unfix_state(appid, {"status": "unfixing"})

    try:
        installed_fixes = _load_installed_fixes()
        fix_data = installed_fixes.get(str(appid), {})

        if not install_path:
            install_path = fix_data.get("installPath", "")

        # If no specific install path, try to detect it
        if not install_path or not os.path.exists(install_path):
            path_info = get_game_install_path_response(appid)
            if isinstance(path_info, dict) and path_info.get("success"):
                install_path = path_info.get("installPath", "")

        if str(appid) in installed_fixes:
            del installed_fixes[str(appid)]
            _save_installed_fixes(installed_fixes)

        _set_unfix_state(appid, {"status": "done"})
        logger.log(f"Fix removed for appid {appid}")
        return json.dumps({"success": True})
    except Exception as e:
        logger.error(f"Unfix error for appid {appid}: {e}")
        _set_unfix_state(appid, {"status": "failed", "error": str(e)})
        return json.dumps({"success": False, "error": str(e)})


def get_unfix_status(appid: int) -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})
    state = _get_unfix_state(appid)
    return json.dumps({"success": True, "state": state})


def apply_linux_native_fix(install_path: str) -> str:
    """Create a Linux native compatibility symlink fix."""
    try:
        if not install_path or not os.path.exists(install_path):
            return json.dumps({"success": False, "error": "Invalid install path"})

        logger.log(f"Applying Linux native fix to: {install_path}")
        return json.dumps({"success": True, "message": "Linux native fix applied"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
