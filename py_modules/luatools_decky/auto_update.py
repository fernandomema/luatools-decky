from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import sys
import zipfile
from typing import Any, Dict, Optional

from .api_manifest import store_last_message
from .config import (
    UPDATE_CHECK_INTERVAL_SECONDS,
    UPDATE_CONFIG_FILE,
    UPDATE_PENDING_INFO,
    UPDATE_PENDING_ZIP,
)
from .http_client import ensure_http_client, get_http_client
from .logger import logger
from .paths import backend_path, get_plugin_dir
from .steam_utils import detect_steam_install_path
from .utils import (
    get_plugin_version,
    parse_version,
    read_json,
    write_json,
)

_UPDATE_CHECK_THREAD: Optional[threading.Thread] = None
_AUTO_UPDATE_ENABLED = False


def apply_pending_update_if_any() -> str:
    pending_zip = backend_path(UPDATE_PENDING_ZIP)
    pending_info = backend_path(UPDATE_PENDING_INFO)
    if not os.path.exists(pending_zip):
        return ""

    try:
        logger.log(f"AutoUpdate: Applying pending update from {pending_zip}")
        with zipfile.ZipFile(pending_zip, "r") as archive:
            archive.extractall(get_plugin_dir())
        try:
            os.remove(pending_zip)
        except Exception:
            pass
        try:
            if os.path.exists(pending_info):
                os.remove(pending_info)
        except Exception:
            pass
        msg = "Update applied successfully."
        logger.log(f"AutoUpdate: {msg}")
        return msg
    except Exception as exc:
        logger.warn(f"AutoUpdate: Apply failed: {exc}")
        return ""


def _check_for_updates() -> Optional[Dict[str, Any]]:
    update_config = read_json(backend_path(UPDATE_CONFIG_FILE))
    github = update_config.get("github", {})
    owner = github.get("owner", "")
    repo = github.get("repo", "")
    asset_name = github.get("asset_name", "")

    if not owner or not repo:
        logger.warn("AutoUpdate: Missing owner/repo in update config")
        return None

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    logger.log(f"AutoUpdate: Checking {api_url}")

    try:
        client = ensure_http_client("AutoUpdate")
        resp = client.get(api_url, headers={"Accept": "application/json", "User-Agent": "LuaTools"})
        if resp.status_code != 200:
            logger.warn(f"AutoUpdate: GitHub API returned {resp.status_code}")
            return None

        data = resp.json()
        latest_tag = data.get("tag_name", "") or data.get("name", "")
        current_version = get_plugin_version()
        logger.log(f"AutoUpdate: current={current_version}, latest={latest_tag}")

        if parse_version(latest_tag) <= parse_version(current_version):
            logger.log("AutoUpdate: Already up-to-date")
            return None

        if not asset_name:
            assets = data.get("assets", [])
            if assets:
                asset_name = assets[0].get("name", "")

        download_url = None
        for asset in data.get("assets", []):
            if asset.get("name") == asset_name:
                download_url = asset.get("browser_download_url")
                break

        if not download_url:
            logger.warn(f"AutoUpdate: Asset '{asset_name}' not found in release")
            return None

        logger.log(f"AutoUpdate: Downloading {download_url}")
        zip_resp = client.get(download_url, follow_redirects=True)
        if zip_resp.status_code != 200:
            logger.warn(f"AutoUpdate: Download failed: {zip_resp.status_code}")
            return None

        pending_zip = backend_path(UPDATE_PENDING_ZIP)
        with open(pending_zip, "wb") as f:
            f.write(zip_resp.content)

        pending_info_path = backend_path(UPDATE_PENDING_INFO)
        write_json(pending_info_path, {
            "version": latest_tag,
            "downloaded_at": time.time(),
        })

        logger.log(f"AutoUpdate: Downloaded update {latest_tag}")
        return {"version": latest_tag}

    except Exception as exc:
        logger.warn(f"AutoUpdate: Check failed: {exc}")
        return None


def check_for_updates_now() -> Dict[str, Any]:
    result = _check_for_updates()
    if result:
        return {"success": True, "update_available": True, "version": result["version"]}
    return {"success": True, "update_available": False}


def _background_update_loop() -> None:
    while _AUTO_UPDATE_ENABLED:
        try:
            result = _check_for_updates()
            if result:
                logger.log(f"AutoUpdate: Background check found update {result['version']}")
        except Exception as exc:
            logger.warn(f"AutoUpdate: Background check error: {exc}")
        for _ in range(UPDATE_CHECK_INTERVAL_SECONDS):
            if not _AUTO_UPDATE_ENABLED:
                return
            time.sleep(1)


def start_auto_update_background_check() -> None:
    global _UPDATE_CHECK_THREAD, _AUTO_UPDATE_ENABLED
    if _UPDATE_CHECK_THREAD and _UPDATE_CHECK_THREAD.is_alive():
        return
    _AUTO_UPDATE_ENABLED = True
    _UPDATE_CHECK_THREAD = threading.Thread(target=_background_update_loop, daemon=True)
    _UPDATE_CHECK_THREAD.start()
    logger.log("AutoUpdate: Background check started")


def stop_auto_update_background_check() -> None:
    global _AUTO_UPDATE_ENABLED
    _AUTO_UPDATE_ENABLED = False
    logger.log("AutoUpdate: Background check stopped")


def restart_steam() -> bool:
    try:
        # Try systemd user service (Steam Deck Game Mode)
        try:
            uid = 1000  # deck user
            bus = f"unix:path=/run/user/{uid}/bus"
            r = subprocess.run(
                ["sudo", "-u", "deck", "env",
                 f"DBUS_SESSION_BUS_ADDRESS={bus}",
                 "systemctl", "--user", "restart", "steam-launcher.service"],
                capture_output=True,
                timeout=30,
            )
            if r.returncode == 0:
                logger.log("Restarting Steam via systemd steam-launcher.service")
                return True
            logger.log(f"systemctl restart failed (exit={r.returncode}): {r.stderr.decode().strip()}")
        except Exception as exc:
            logger.log(f"systemctl restart exception: {exc}")

        # Fallback: steam.sh --restart (Desktop Mode)
        steam_root = detect_steam_install_path()
        if steam_root:
            steam_sh = os.path.join(steam_root, "steam.sh")
            if os.path.isfile(steam_sh):
                subprocess.Popen(
                    [steam_sh, "--restart"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.log("Restarting Steam via steam.sh --restart")
                return True

        return False
    except Exception as exc:
        logger.log(f"restart_steam exception: {exc}")
        return False
