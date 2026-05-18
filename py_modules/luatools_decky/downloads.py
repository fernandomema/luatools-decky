from __future__ import annotations

import base64
import json
import os
import re
import shutil
import threading
import time
import subprocess
from typing import Dict, Any, Optional

from .config import (
    APPID_LOG_FILE,
    LOADED_APPS_FILE,
    USER_AGENT,
    WEBKIT_DIR_NAME,
    WEB_UI_ICON_FILE,
    WEB_UI_JS_FILE,
)
from .http_client import ensure_http_client
from .logger import logger
from .paths import backend_path, public_path
from .steam_utils import detect_steam_install_path, has_lua_for_app
from .utils import count_apis, ensure_temp_download_dir, normalize_manifest_text, read_text, write_text

DOWNLOAD_STATE: Dict[int, Dict[str, Any]] = {}
DOWNLOAD_LOCK = threading.Lock()

APP_NAME_CACHE: Dict[int, str] = {}
APP_NAME_CACHE_LOCK = threading.Lock()

LAST_API_CALL_TIME = 0
API_CALL_MIN_INTERVAL = 0.3

APPLIST_DATA: Dict[int, str] = {}
APPLIST_LOADED = False
APPLIST_LOCK = threading.Lock()
APPLIST_FILE_NAME = "all-appids.json"
APPLIST_URL = "https://applist.morrenus.xyz/"
APPLIST_DOWNLOAD_TIMEOUT = 300

GAMES_DB_FILE_NAME = "games.json"
GAMES_DB_URL = "https://toolsdb.piqseu.cc/games.json"
GAMES_DB_DATA: Dict[str, Any] = {}
GAMES_DB_LOADED = False
GAMES_DB_LOCK = threading.Lock()


def get_steam_libraries() -> str:
    try:
        libs = []
        seen_real = set()

        def _add_lib(p: str):
            real = os.path.realpath(p)
            if real not in seen_real and os.path.isdir(p):
                seen_real.add(real)
                libs.append(p)

        steam_path = detect_steam_install_path()
        if steam_path:
            _add_lib(steam_path)
            vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
            if os.path.exists(vdf_path):
                with open(vdf_path, "r", encoding="utf-8") as f:
                    content = f.read()
                for m in re.finditer(r'"path"\s*"([^"]+)"', content):
                    _add_lib(m.group(1))
        result = []
        for p in libs:
            label = os.path.basename(os.path.normpath(p))
            result.append({"path": p, "label": label, "free": _get_free_space_gb(p)})
        return json.dumps({"success": True, "libraries": result})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def _get_free_space_gb(path: str) -> int:
    try:
        import shutil
        _, _, free = shutil.disk_usage(path)
        return free // (1024**3)
    except Exception:
        return 0

_DOTNET_ROOT = os.path.expanduser("~/.dotnet")

def _ensure_dotnet() -> str | None:
    dotnet = shutil.which("dotnet") or os.path.join(_DOTNET_ROOT, "dotnet")
    if dotnet and os.path.exists(dotnet):
        return dotnet
    logger.log(".NET 9 not found, installing...")
    try:
        os.makedirs(_DOTNET_ROOT, exist_ok=True)
        script = os.path.join(_DOTNET_ROOT, "dotnet-install.sh")
        import urllib.request
        urllib.request.urlretrieve("https://dot.net/v1/dotnet-install.sh", script)
        os.chmod(script, 0o755)
        subprocess.run([script, "--channel", "9.0", "--runtime", "dotnet", "--install-dir", _DOTNET_ROOT], check=True, timeout=300)
        os.remove(script)
        dotnet_path = os.path.join(_DOTNET_ROOT, "dotnet")
        if os.path.exists(dotnet_path):
            return dotnet_path
    except Exception as e:
        logger.warn(f".NET install failed: {e}")
    return None

_DEPS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "deps")

def _extract_depot_downloader() -> str | None:
    target_dir = _DEPS_DIR
    os.makedirs(target_dir, exist_ok=True)
    dll_target = os.path.join(target_dir, "DepotDownloader.dll")

    if os.path.exists(dll_target):
        return dll_target

    appimage = os.path.expanduser("~/.local/share/ACCELA/ACCELA.AppImage")
    if not os.path.exists(appimage):
        logger.warn("ACCELA AppImage not found for extraction")
        return None

    try:
        import subprocess, shutil, tempfile
        tmp = tempfile.mkdtemp(prefix="accela-extract-")
        subprocess.run([appimage, "--appimage-extract"], cwd=tmp, capture_output=True, timeout=60)
        src = os.path.join(tmp, "squashfs-root", "bin", "src", "deps")
        if os.path.isdir(src):
            for fname in os.listdir(src):
                full = os.path.join(src, fname)
                if os.path.isfile(full):
                    shutil.copy2(full, os.path.join(target_dir, fname))
            logger.log(f"Extracted {len(os.listdir(src))} files from AppImage deps")
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.exists(dll_target):
            return dll_target
    except Exception as e:
        logger.warn(f"Failed to extract DepotDownloader: {e}")
    return None

def _parse_lua_for_depots(lua: str) -> tuple:
    app_id = None
    game_name = "Unknown"
    install_dir = None
    depots: Dict[str, dict] = {}
    manifest_sizes: Dict[str, str] = {}
    app_token = None

    # Try to detect the main app_id from a single-arg addappid(XXXXX) or
    # from the comment header "-- NNNNNN's Lua" before any depot parsing.
    single_m = re.search(r'^addappid\s*\(\s*(\d+)\s*\)', lua, re.MULTILINE)
    if single_m:
        app_id = single_m.group(1)
    else:
        # Fallback: first line comment like "-- 2582320's Lua"
        header_m = re.search(r'--\s*(\d+)\'s Lua', lua)
        if header_m:
            app_id = header_m.group(1)

    # Extract game name from second non-empty comment line
    lines = [l.strip() for l in lua.split('\n') if l.strip()]
    for line in lines[1:4]:
        if line.startswith('--') and not any(x in line for x in ["Created", "Website", "Total", "Shared", "Lua"]):
            game_name = line.lstrip('-').strip()
            break

    # All addappid with 3 args are depots (key-bearing)
    for m in re.finditer(r'addappid\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*"([^"]*)"\s*\)', lua):
        aid, ver, key = m.group(1), m.group(2), m.group(3)
        if app_id is None:
            # No single-arg found earlier; treat first 3-arg as app (old format)
            app_id = aid
            app_token = key
        elif aid == app_id:
            # Some formats put the main app as a 3-arg addappid too
            app_token = key
        else:
            desc_m = re.search(rf'addappid\s*\(\s*{re.escape(aid)}\s*,\s*\d+\s*,\s*"[^"]*"\s*\)\s*--\s*(.+?)$', lua, re.MULTILINE)
            desc = desc_m.group(1).strip() if desc_m else f"Depot {aid}"
            if key:
                depots[aid] = {"key": key, "desc": desc}

    dir_m = re.search(r'--\s*Found official install directory:\s*(\S+)', lua)
    if dir_m:
        install_dir = dir_m.group(1)
    if not install_dir:
        lines = lua.strip().split('\n')
        if len(lines) >= 2:
            second = lines[1].strip().lstrip('-').strip()
            if second and not second.startswith(("Total", "Created", "Website")):
                install_dir = second
    if not install_dir:
        install_dir = game_name.replace(" ", "_") if game_name != "Unknown" else None
    if not install_dir:
        install_dir = f"App_{app_id}"

    for m in re.finditer(r'(?:--\s*)?setManifestid\(\s*(\d+)\s*,\s*"([^"]*)"\s*,\s*(\d+)\s*\)', lua):
        mid_depot, mid_val, size = m.group(1), m.group(2), m.group(3)
        manifest_sizes[mid_depot] = mid_val

    token_m = re.search(r'addtoken\s*\(\s*\d+\s*,\s*"([^"]+)"\s*\)', lua)
    if token_m:
        app_token = app_token or token_m.group(1)

    return app_id, game_name, install_dir, depots, manifest_sizes, app_token

def _run_depot_downloader(appid: int, lua_content: str, destination_path: str, archive) -> None:
    def _msg(txt):
        _set_download_state(int(appid), {"message": txt})

    _msg("Parsing lua for depots...")
    app_id, game_name, install_dir, depots, manifest_sizes, app_token = _parse_lua_for_depots(lua_content)
    _msg(f"Parsed: app={app_id}, depots={list(depots.keys())}, manifests={manifest_sizes}")
    if not app_id or not depots:
        logger.warn("No depots found in lua, cannot download game")
        _msg("FAILED: no depots found in lua")
        return
    if not install_dir:
        install_dir = f"App_{app_id}"

    _msg("Checking .NET 9...")
    dotnet = _ensure_dotnet()
    if not dotnet:
        logger.warn(".NET 9 not available, skipping game download")
        _msg("FAILED: .NET 9 not found")
        return
    _msg(f".NET found: {dotnet}")

    _msg("Extracting DepotDownloader.dll...")
    dll = _extract_depot_downloader()
    if not dll:
        logger.warn("DepotDownloader.dll not found, skipping game download")
        _msg("FAILED: DepotDownloader.dll not found")
        return
    _msg(f"DLL found: {dll}")

    download_dir = os.path.join(destination_path, "steamapps", "common", install_dir)
    os.makedirs(download_dir, exist_ok=True)

    temp_dir = ensure_temp_download_dir()
    keys_path = os.path.join(temp_dir, f"depotkeys_{appid}.vdf")

    steam_path = detect_steam_install_path()
    if steam_path:
        depotcache_dir = os.path.join(steam_path, "depotcache")
    else:
        depotcache_dir = os.path.join(destination_path, "steamapps", "depotcache")
    os.makedirs(depotcache_dir, exist_ok=True)

    total_size = 0
    selected_depots = []
    commands = []

    _msg(f"Building commands for {len(depots)} depot(s)...")
    for depot_id, depot_info in depots.items():
        manifest_id = manifest_sizes.get(depot_id)
        if not manifest_id:
            logger.log(f"No manifest ID for depot {depot_id}, skipping")
            _msg(f"SKIP depot {depot_id}: no manifest ID")
            continue
        manifest_file = os.path.join(depotcache_dir, f"{depot_id}_{manifest_id}.manifest")
        if not os.path.exists(manifest_file):
            for n in archive.namelist():
                if n.endswith(".manifest") and depot_id in n:
                    data = archive.read(n)
                    with open(manifest_file, "wb") as f:
                        f.write(data)
                    break
        if not os.path.exists(manifest_file):
            logger.warn(f"Manifest file not found for depot {depot_id}, skipping")
            continue

        try:
            size = int(depot_info.get("size", 0) or 0)
        except (ValueError, TypeError):
            size = 0
        total_size += size
        selected_depots.append(depot_id)

        commands.append([
            dotnet, str(dll),
            "-app", str(app_id),
            "-depot", str(depot_id),
            "-manifest", str(manifest_id),
            "-manifestfile", str(manifest_file),
            "-depotkeys", str(keys_path),
            "-max-downloads", "16",
            "-dir", str(download_dir),
            "-validate",
        ])

    if not commands:
        logger.warn("No valid DepotDownloader commands to run")
        _msg("FAILED: no commands to run (all depots skipped)")
        return

    with open(keys_path, "w") as f:
        for d_id in selected_depots:
            key = depots[d_id].get("key")
            if key:
                f.write(f"{d_id};{key}\n")

    _set_download_state(int(app_id), {
        "status": "downloading_game", "bytesRead": 0,
        "totalBytes": total_size or 1,
        "message": f"Iniciando descarga de {game_name}..."})

    for i, cmd in enumerate(commands):
        if _is_download_cancelled(int(app_id)):
            return
        depot_id = selected_depots[i]
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        env.pop("STEAM_RUNTIME", None)
        if dotnet and _DOTNET_ROOT:
            env["DOTNET_ROOT"] = _DOTNET_ROOT
            env["PATH"] = _DOTNET_ROOT + os.pathsep + env.get("PATH", "")

        _set_download_state(int(app_id), {
            "message": f"Descargando depot {depot_id} ({i+1}/{len(commands)})..."})

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env,
            )
            pct_re = re.compile(r"(\d{1,3}(?:\.\d{1,2})?)%")
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    clean = line.strip()
                    if clean:
                        logger.log(f"DD: {clean[:200]}")
                    m = pct_re.search(clean)
                    if m:
                        pct = float(m.group(1))
                        overall = ((i + pct / 100.0) / len(commands)) * 100
                        _set_download_state(int(app_id), {
                            "percent": round(overall, 1),
                            "message": f"Descargando... {pct:.1f}% (depot {i+1}/{len(commands)})",
                        })
            rc = proc.poll() or 0
            if rc != 0:
                logger.warn(f"DepotDownloader exit code {rc} for depot {depot_id}")
        except Exception as e:
            logger.warn(f"DepotDownloader failed for depot {depot_id}: {e}")

    try:
        os.remove(keys_path)
    except Exception:
        pass

    acf_path = os.path.join(destination_path, "steamapps", f"appmanifest_{app_id}.acf")
    try:
        size_on_disk = 0
        for dirpath, dirnames, filenames in os.walk(download_dir):
            for fn in filenames:
                try:
                    size_on_disk += os.path.getsize(os.path.join(dirpath, fn))
                except Exception:
                    pass
        now = int(time.time())

        # Separate main depot from shared depots (shared depots have appid != app_id
        # and their appid is from a different app, e.g. 228989 from 228980)
        main_depots = []
        shared_depots = []
        for depot_id in selected_depots:
            # Shared depots are depots whose id doesn't start with the same app prefix
            # and whose size in the lua indicates they come from another app.
            desc = depots.get(depot_id, {}).get("desc", "")
            if "Shared from App" in desc:
                # Extract parent app from description "... (Shared from App XXXXXX)"
                m_shared = re.search(r'Shared from App (\d+)', desc)
                shared_depots.append((depot_id, m_shared.group(1) if m_shared else "228980"))
            else:
                main_depots.append(depot_id)

        acf_lines = [
            '"AppState"',
            '{',
            f'\t"appid"\t\t"{app_id}"',
            '\t"universe"\t\t"1"',
            f'\t"name"\t\t"{game_name}"',
            '\t"StateFlags"\t\t"4"',
            f'\t"installdir"\t\t"{install_dir}"',
            f'\t"LastUpdated"\t\t"{now}"',
            '\t"LastPlayed"\t\t"0"',
            f'\t"SizeOnDisk"\t\t"{size_on_disk}"',
            '\t"StagingSize"\t\t"0"',
            '\t"buildid"\t\t"0"',
            '\t"LastOwner"\t\t"0"',
            '\t"UpdateResult"\t\t"0"',
            '\t"BytesToDownload"\t\t"0"',
            '\t"BytesDownloaded"\t\t"0"',
            '\t"BytesToStage"\t\t"0"',
            '\t"BytesStaged"\t\t"0"',
            '\t"AutoUpdateBehavior"\t\t"0"',
            '\t"AllowOtherDownloadsWhileRunning"\t\t"0"',
            '\t"InstalledDepots"',
            '\t{',
        ]
        for depot_id in main_depots:
            mid = manifest_sizes.get(depot_id, "0")
            acf_lines.append(f'\t\t"{depot_id}"')
            acf_lines.append('\t\t{')
            acf_lines.append(f'\t\t\t"manifest"\t\t"{mid}"')
            acf_lines.append(f'\t\t\t"size"\t\t"{size_on_disk}"')
            acf_lines.append('\t\t}')
        for depot_id, _ in shared_depots:
            mid = manifest_sizes.get(depot_id, "0")
            acf_lines.append(f'\t\t"{depot_id}"')
            acf_lines.append('\t\t{')
            acf_lines.append(f'\t\t\t"manifest"\t\t"{mid}"')
            acf_lines.append(f'\t\t\t"size"\t\t"0"')
            acf_lines.append('\t\t}')
        acf_lines.append('\t}')
        if shared_depots:
            acf_lines.append('\t"SharedDepots"')
            acf_lines.append('\t{')
            for depot_id, parent_app in shared_depots:
                acf_lines.append(f'\t\t"{depot_id}"\t\t"{parent_app}"')
            acf_lines.append('\t}')
        acf_lines.append('\t"UserConfig"')
        acf_lines.append('\t{')
        acf_lines.append('\t}')
        acf_lines.append('\t"MountedConfig"')
        acf_lines.append('\t{')
        acf_lines.append('\t}')
        acf_lines.append('}')
        with open(acf_path, "w", encoding="utf-8") as f:
            f.write("\n".join(acf_lines) + "\n")
        logger.log(f"Created ACF: {acf_path}")
        # Register the app in libraryfolders.vdf so Steam shows it in the library
        try:
            _register_in_libraryfolders(app_id, destination_path, size_on_disk)
        except Exception as e:
            logger.warn(f"Failed to register in libraryfolders: {e}")
    except Exception as e:
        logger.warn(f"Failed to create ACF: {e}")

    logger.log(f"Game download complete: {game_name}")


def _register_in_libraryfolders(app_id: str, destination_path: str, size_on_disk: int) -> None:
    """Add the appid entry to libraryfolders.vdf so Steam shows the game in the library."""
    steam_path = detect_steam_install_path()
    if not steam_path:
        return
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(vdf_path):
        return
    with open(vdf_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Already registered?
    if f'"{app_id}"' in content:
        logger.log(f"App {app_id} already in libraryfolders.vdf")
        return

    dest_real = os.path.realpath(destination_path)

    # Find the library entry whose path matches destination_path
    # VDF structure: each library block has "path" and "apps" sections
    # We find the apps block of the matching library and insert there
    lines = content.split("\n")
    target_lib_index = None
    current_path = None
    for i, line in enumerate(lines):
        m = re.search(r'"path"\s*"([^"]+)"', line)
        if m:
            current_path = m.group(1)
        if line.strip() == '"apps"' and current_path:
            if os.path.realpath(current_path) == dest_real:
                target_lib_index = i
                break

    if target_lib_index is None:
        # Fall back: insert in first library (index 0 = default steam library)
        for i, line in enumerate(lines):
            if line.strip() == '"apps"':
                target_lib_index = i
                break

    if target_lib_index is None:
        logger.warn("Could not find apps section in libraryfolders.vdf")
        return

    # Find the closing brace of that apps block
    depth = 0
    insert_before = None
    for i in range(target_lib_index, len(lines)):
        stripped = lines[i].strip()
        if stripped == "{":
            depth += 1
        elif stripped == "}":
            depth -= 1
            if depth == 0:
                insert_before = i
                break

    if insert_before is None:
        logger.warn("Could not find end of apps block in libraryfolders.vdf")
        return

    new_entry = f'\t\t\t"{app_id}"\t\t"{size_on_disk}"'
    lines.insert(insert_before, new_entry)
    with open(vdf_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.log(f"Registered app {app_id} in libraryfolders.vdf (size={size_on_disk})")


def _get_cookie_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "data", "ryuu_cookie.txt")

def _get_user_settings_dir() -> str:
    try:
        import decky
        return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR)
    except Exception:
        fallback = os.path.expanduser("~/homebrew/settings/luatools-decky")
        if os.path.isdir(fallback):
            return fallback
        return ""

def _get_api_json_path() -> str:
    return backend_path("api.json")

def load_ryu_cookie() -> str:
    try:
        path = _get_cookie_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception as e:
        logger.warn(f"Error reading ryuu cookie: {e}")
    return ""

def save_ryu_cookie(cookie_content: str) -> str:
    try:
        path = _get_cookie_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        clean_cookie = cookie_content.strip()
        if clean_cookie and not clean_cookie.startswith("session="):
            clean_cookie = f"session={clean_cookie}"
        with open(path, "w", encoding="utf-8") as f:
            f.write(clean_cookie)
        logger.log(f"Ryuu cookie saved (size: {len(clean_cookie)})")
        return json.dumps({"success": True, "message": "Cookie saved!"})
    except Exception as e:
        logger.error(f"Error saving cookie: {e}")
        return json.dumps({"success": False, "error": str(e)})

def _get_user_api_json_path() -> str:
    settings_dir = _get_user_settings_dir()
    if settings_dir:
        return os.path.join(settings_dir, "user_apis.json")
    return ""

def save_user_apis(data: dict) -> bool:
    path = _get_user_api_json_path()
    if not path:
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logger.warn(f"Failed to save user APIs: {e}")
        return False

def load_user_apis() -> dict:
    path = _get_user_api_json_path()
    if not path or not os.path.exists(path):
        return {"api_list": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return json.loads(content)
    except Exception as e:
        logger.warn(f"Failed to load user APIs: {e}")
    return {"api_list": []}

def update_morrenus_key(key_content: str) -> str:
    try:
        key_content = key_content.strip()
        if not key_content:
            return json.dumps({"success": False, "error": "Key cannot be empty."})
        root_data = load_user_apis()
        if "api_list" not in root_data:
            root_data["api_list"] = []
        api_list = root_data["api_list"]
        found = False
        new_url = f"https://hubcapmanifest.com/api/v1/manifest/<appid>?api_key={key_content}"
        for api in api_list:
            if "morrenus" in api.get("name", "").lower() or "morrenus.xyz" in api.get("url", ""):
                api["url"] = new_url
                api["enabled"] = True
                found = True
                break
        if not found:
            new_entry = {
                "name": "Morrenus",
                "url": new_url,
                "success_code": 200,
                "unavailable_code": 404,
                "enabled": True,
            }
            api_list.insert(0, new_entry)
        root_data["api_list"] = api_list
        if save_user_apis(root_data):
            return json.dumps({"success": True, "message": "Morrenus key saved to user config!"})
        return json.dumps({"success": False, "error": "Could not save to user settings directory"})
    except Exception as e:
        logger.error(f"Error updating Morrenus key: {e}")
        return json.dumps({"success": False, "error": str(e)})


def _set_download_state(appid: int, update: dict) -> None:
    with DOWNLOAD_LOCK:
        state = DOWNLOAD_STATE.get(appid) or {}
        state.update(update)
        DOWNLOAD_STATE[appid] = state

def _get_download_state(appid: int) -> dict:
    with DOWNLOAD_LOCK:
        return DOWNLOAD_STATE.get(appid, {}).copy()

def _loaded_apps_path() -> str:
    return backend_path(LOADED_APPS_FILE)

def _appid_log_path() -> str:
    return backend_path(APPID_LOG_FILE)


def _fetch_app_name(appid: int) -> str:
    global LAST_API_CALL_TIME
    with APP_NAME_CACHE_LOCK:
        if appid in APP_NAME_CACHE:
            cached = APP_NAME_CACHE[appid]
            if cached:
                return cached
    applist_name = _get_app_name_from_applist(appid)
    if applist_name:
        with APP_NAME_CACHE_LOCK:
            APP_NAME_CACHE[appid] = applist_name
        return applist_name
    with APP_NAME_CACHE_LOCK:
        time_since_last_call = time.time() - LAST_API_CALL_TIME
        if time_since_last_call < API_CALL_MIN_INTERVAL:
            time.sleep(API_CALL_MIN_INTERVAL - time_since_last_call)
        LAST_API_CALL_TIME = time.time()
    client = ensure_http_client("_fetch_app_name")
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
        resp = client.get(url, follow_redirects=True, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        entry = data.get(str(appid)) or data.get(int(appid)) or {}
        if isinstance(entry, dict):
            inner = entry.get("data") or {}
            name = inner.get("name")
            if isinstance(name, str) and name.strip():
                name = name.strip()
                with APP_NAME_CACHE_LOCK:
                    APP_NAME_CACHE[appid] = name
                return name
    except Exception as exc:
        logger.warn(f"_fetch_app_name failed for {appid}: {exc}")
    with APP_NAME_CACHE_LOCK:
        APP_NAME_CACHE[appid] = ""
    return ""


def _append_loaded_app(appid: int, name: str) -> None:
    try:
        path = _loaded_apps_path()
        lines = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        prefix = f"{appid}:"
        lines = [line for line in lines if not line.startswith(prefix)]
        lines.append(f"{appid}:{name}")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except Exception as exc:
        logger.warn(f"_append_loaded_app failed for {appid}: {exc}")

def _remove_loaded_app(appid: int) -> None:
    try:
        path = _loaded_apps_path()
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        prefix = f"{appid}:"
        new_lines = [line for line in lines if not line.startswith(prefix)]
        if len(new_lines) != len(lines):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(new_lines) + ("\n" if new_lines else ""))
    except Exception as exc:
        logger.warn(f"_remove_loaded_app failed for {appid}: {exc}")

def _log_appid_event(action: str, appid: int, name: str) -> None:
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        line = f"[{action}] {appid} - {name} - {stamp}\n"
        with open(_appid_log_path(), "a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception as exc:
        logger.warn(f"_log_appid_event failed: {exc}")

def _preload_app_names_cache() -> None:
    try:
        log_path = _appid_log_path()
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as handle:
                for line in handle.read().splitlines():
                    if "]" in line and " - " in line:
                        try:
                            parts = line.split("]", 1)
                            if len(parts) < 2:
                                continue
                            content = parts[1].strip()
                            content_parts = content.split(" - ", 2)
                            if len(content_parts) >= 2:
                                appid_str = content_parts[0].strip()
                                name = content_parts[1].strip()
                                appid = int(appid_str)
                                if name and not name.startswith("Unknown"):
                                    with APP_NAME_CACHE_LOCK:
                                        APP_NAME_CACHE[appid] = name
                        except (ValueError, IndexError):
                            continue
    except Exception as exc:
        logger.warn(f"_preload_app_names_cache from logs failed: {exc}")
    try:
        path = _loaded_apps_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle.read().splitlines():
                    if ":" in line:
                        parts = line.split(":", 1)
                        try:
                            appid = int(parts[0].strip())
                            name = parts[1].strip()
                            if name:
                                with APP_NAME_CACHE_LOCK:
                                    APP_NAME_CACHE[appid] = name
                        except (ValueError, IndexError):
                            continue
    except Exception as exc:
        logger.warn(f"_preload_app_names_cache from loaded_apps failed: {exc}")
    try:
        _load_applist_into_memory()
    except Exception as exc:
        logger.warn(f"_preload_app_names_cache from applist failed: {exc}")

def _get_loaded_app_name(appid: int) -> str:
    try:
        path = _loaded_apps_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle.read().splitlines():
                    if line.startswith(f"{appid}:"):
                        name = line.split(":", 1)[1].strip()
                        if name:
                            return name
    except Exception:
        pass
    return _get_app_name_from_applist(appid)

def _applist_file_path() -> str:
    temp_dir = ensure_temp_download_dir()
    return os.path.join(temp_dir, APPLIST_FILE_NAME)

def _load_applist_into_memory() -> None:
    global APPLIST_DATA, APPLIST_LOADED
    with APPLIST_LOCK:
        if APPLIST_LOADED:
            return
        file_path = _applist_file_path()
        if not os.path.exists(file_path):
            logger.log("Applist file not found, skipping load")
            APPLIST_LOADED = True
            return
        try:
            logger.log("Loading applist into memory...")
            with open(file_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                count = 0
                for entry in data:
                    if isinstance(entry, dict):
                        appid = entry.get("appid")
                        name = entry.get("name")
                        if appid and name and isinstance(name, str) and name.strip():
                            APPLIST_DATA[int(appid)] = name.strip()
                            count += 1
                logger.log(f"Loaded {count} app names from applist")
            else:
                logger.warn("Applist file has invalid format")
            APPLIST_LOADED = True
        except Exception as exc:
            logger.warn(f"Failed to load applist: {exc}")
            APPLIST_LOADED = True

def _get_app_name_from_applist(appid: int) -> str:
    global APPLIST_DATA, APPLIST_LOADED
    if not APPLIST_LOADED:
        _load_applist_into_memory()
    with APPLIST_LOCK:
        return APPLIST_DATA.get(int(appid), "")

def _ensure_applist_file() -> None:
    file_path = _applist_file_path()
    if os.path.exists(file_path):
        logger.log("Applist file already exists, skipping download")
        return
    logger.log("Applist file not found, downloading...")
    client = ensure_http_client("DownloadApplist")
    try:
        resp = client.get(APPLIST_URL, follow_redirects=True, timeout=APPLIST_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        try:
            data = resp.json()
            if not isinstance(data, list):
                logger.warn("Downloaded applist has invalid format")
                return
        except json.JSONDecodeError as exc:
            logger.warn(f"Downloaded applist is not valid JSON: {exc}")
            return
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        logger.log(f"Successfully downloaded applist file ({len(data)} entries)")
    except Exception as exc:
        logger.warn(f"Failed to download applist: {exc}")

def init_applist() -> None:
    try:
        _ensure_applist_file()
        _load_applist_into_memory()
    except Exception as exc:
        logger.warn(f"Applist initialization failed: {exc}")

def _games_db_file_path() -> str:
    temp_dir = ensure_temp_download_dir()
    return os.path.join(temp_dir, GAMES_DB_FILE_NAME)

def _load_games_db_into_memory() -> None:
    global GAMES_DB_DATA, GAMES_DB_LOADED
    with GAMES_DB_LOCK:
        if GAMES_DB_LOADED:
            return
        file_path = _games_db_file_path()
        if not os.path.exists(file_path):
            logger.log("Games DB file not found, skipping load")
            GAMES_DB_LOADED = True
            return
        try:
            logger.log("Loading Games DB into memory...")
            with open(file_path, "r", encoding="utf-8") as handle:
                GAMES_DB_DATA = json.load(handle)
            logger.log(f"Loaded Games DB ({len(GAMES_DB_DATA)} entries)")
            GAMES_DB_LOADED = True
        except Exception as exc:
            logger.warn(f"Failed to load Games DB: {exc}")
            GAMES_DB_LOADED = True

def _ensure_games_db_file() -> None:
    file_path = _games_db_file_path()
    logger.log("Downloading Games DB...")
    client = ensure_http_client("DownloadGamesDB")
    try:
        logger.log(f"Downloading Games DB from {GAMES_DB_URL}")
        resp = client.get(GAMES_DB_URL, follow_redirects=True, timeout=60)
        logger.log(f"Games DB download response: status={resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        logger.log("Successfully downloaded Games DB")
    except Exception as exc:
        logger.warn(f"Failed to download Games DB: {exc}")

def init_games_db() -> None:
    try:
        _ensure_games_db_file()
        _load_games_db_into_memory()
    except Exception as exc:
        logger.warn(f"Games DB initialization failed: {exc}")

def get_games_database() -> str:
    if not GAMES_DB_LOADED:
        init_games_db()
    with GAMES_DB_LOCK:
        return json.dumps(GAMES_DB_DATA)

def fetch_app_name(appid: int) -> str:
    return _fetch_app_name(appid)

def _process_and_install_lua(appid: int, zip_path: str, destination_path: Optional[str] = None) -> None:
    import zipfile
    if _is_download_cancelled(appid):
        raise RuntimeError("cancelled")
    base_path = detect_steam_install_path()
    target_dir = os.path.join(base_path or "", "config", "stplug-in")
    os.makedirs(target_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as archive:
        lua_content = None
        for n in archive.namelist():
            if re.fullmatch(r"\d+\.lua", os.path.basename(n)):
                lua_content = archive.read(n).decode("utf-8", errors="replace")
                break
        if not lua_content:
            logger.warn("No lua file found in ZIP, skipping game download")
        elif not destination_path:
            logger.log("No destination_path provided, skipping game download")
        else:
            # Try to estimate total download size from any manifest files present in the zip
            try:
                manifest_total = 0
                for n in archive.namelist():
                    if n.lower().endswith('.manifest'):
                        try:
                            data = archive.read(n)
                            manifest_total += len(data)
                        except Exception:
                            continue
                # If we couldn't estimate, leave as 0 so UI shows unknown
                estimated = manifest_total if manifest_total > 0 else 0
                logger.log(f"Estimated manifest total size: {estimated} bytes for appid={appid}")
                _set_download_state(appid, {"status": "downloading_game", "bytesRead": 0, "totalBytes": estimated, "message": "Preparando DepotDownloader..."})
            except Exception as e:
                logger.warn(f"Failed to estimate manifest sizes: {e}")
                _set_download_state(appid, {"status": "downloading_game", "bytesRead": 0, "totalBytes": 0, "message": "Preparando DepotDownloader..."})
            try:
                _run_depot_downloader(appid, lua_content, destination_path, archive)
            except Exception as e:
                logger.warn(f"Game download failed (non-fatal): {e}")

    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
        try:
            depotcache_dir = os.path.join(base_path or "", "depotcache")
            os.makedirs(depotcache_dir, exist_ok=True)
            accela_manifest_dir = os.path.expanduser("~/.local/share/ACCELA/morrenus_manifests")
            for name in names:
                try:
                    if _is_download_cancelled(appid):
                        raise RuntimeError("cancelled")
                    if name.lower().endswith(".manifest"):
                        pure = os.path.basename(name)
                        data = archive.read(name)
                        out_path = os.path.join(depotcache_dir, pure)
                        with open(out_path, "wb") as manifest_file:
                            manifest_file.write(data)
                        logger.log(f"Extracted manifest -> {out_path}")

                        if accela_manifest_dir:
                            os.makedirs(accela_manifest_dir, exist_ok=True)
                            accela_path = os.path.join(accela_manifest_dir, pure)
                            with open(accela_path, "wb") as mf:
                                mf.write(data)
                            logger.log(f"Copied manifest -> {accela_path}")
                except Exception as manifest_exc:
                    logger.warn(f"Failed to extract manifest {name}: {manifest_exc}")
        except Exception as depot_exc:
            logger.warn(f"depotcache extraction failed: {depot_exc}")

        candidates = []
        for name in names:
            pure = os.path.basename(name)
            if re.fullmatch(r"\d+\.lua", pure):
                candidates.append(name)

        if _is_download_cancelled(appid):
            raise RuntimeError("cancelled")

        chosen = None
        preferred = f"{appid}.lua"
        for name in candidates:
            if os.path.basename(name) == preferred:
                chosen = name
                break
        if chosen is None and candidates:
            chosen = candidates[0]
        if not chosen:
            raise RuntimeError("No numeric .lua file found in zip")

        data = archive.read(chosen)
        try:
            text = data.decode("utf-8")
        except Exception:
            text = data.decode("utf-8", errors="replace")

        processed_lines = []
        for line in text.splitlines(True):
            stripped = line.lstrip()
            if stripped.startswith("--") and "setManifestid(" in stripped:
                line = line.replace("--", "", 1)
            processed_lines.append(line)
        processed_text = "".join(processed_lines)

        _set_download_state(appid, {"status": "installing"})
        dest_file = os.path.join(target_dir, f"{appid}.lua")
        if _is_download_cancelled(appid):
            raise RuntimeError("cancelled")
        with open(dest_file, "w", encoding="utf-8") as output:
            output.write(processed_text)
        logger.log(f"Installed lua -> {dest_file}")
        _set_download_state(appid, {"installedPath": dest_file})

    try:
        os.remove(zip_path)
    except Exception:
        try:
            for _ in range(3):
                time.sleep(0.2)
                try:
                    os.remove(zip_path)
                    break
                except Exception:
                    continue
        except Exception:
            pass

def _is_download_cancelled(appid: int) -> bool:
    try:
        return _get_download_state(appid).get("status") == "cancelled"
    except Exception:
        return False

def _download_zip_for_app(appid: int, destination_path: Optional[str] = None):
    client = ensure_http_client("download")
    apis = load_api_manifest()
    if not apis:
        logger.warn("No enabled APIs in manifest")
        _set_download_state(appid, {"status": "failed", "error": "No APIs available"})
        return

    dest_root = ensure_temp_download_dir()
    dest_path = os.path.join(dest_root, f"{appid}.zip")
    _set_download_state(
        appid,
        {"status": "checking", "currentApi": None, "bytesRead": 0, "totalBytes": 0, "dest": dest_path},
    )

    for api in apis:
        name = api.get("name", "Unknown")
        template = api.get("url", "")
        success_code = int(api.get("success_code", 200))
        unavailable_code = int(api.get("unavailable_code", 404))
        url = template.replace("<appid>", str(appid))
        _set_download_state(
            appid, {"status": "checking", "currentApi": name, "bytesRead": 0, "totalBytes": 0}
        )
        logger.log(f"Trying API '{name}' -> {url}")

        try:
            headers = {"User-Agent": USER_AGENT}

            if "ryuu.lol" in url:
                cookie_content = load_ryu_cookie()
                if cookie_content:
                    logger.log(f"Injecting Ryuu cookie for API '{name}'")
                    headers["Cookie"] = cookie_content
                    headers["Referer"] = "https://generator.ryuu.lol/"
                    headers["Authority"] = "generator.ryuu.lol"
                    headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                    headers["Upgrade-Insecure-Requests"] = "1"
                    headers["Sec-Fetch-Dest"] = "document"
                    headers["Sec-Fetch-Mode"] = "navigate"
                    headers["Sec-Fetch-Site"] = "same-origin"
                else:
                    logger.warn("Ryuu API detected, but no cookie found!")

            if _is_download_cancelled(appid):
                logger.log(f"Download cancelled before contacting API '{name}'")
                return

            with client.stream("GET", url, headers=headers, follow_redirects=True, timeout=30) as resp:
                code = resp.status_code
                logger.log(f"API '{name}' status={code}")
                if code == unavailable_code:
                    continue
                if code != success_code:
                    if "ryuu.lol" in url and (code == 403 or code == 401):
                        logger.warn(f"Ryuu access denied ({code}). Check cookie.")
                    continue

                total = int(resp.headers.get("Content-Length", "0") or "0")
                _set_download_state(appid, {"status": "downloading", "bytesRead": 0, "totalBytes": total})

                with open(dest_path, "wb") as output:
                    for chunk in resp.iter_bytes():
                        if not chunk:
                            continue
                        if _is_download_cancelled(appid):
                            logger.log(f"Download cancelled mid-stream for appid={appid}")
                            raise RuntimeError("cancelled")
                        output.write(chunk)
                        state = _get_download_state(appid)
                        read = int(state.get("bytesRead", 0)) + len(chunk)
                        _set_download_state(appid, {"bytesRead": read})
                        if _is_download_cancelled(appid):
                            logger.log(f"Download cancelled after writing chunk for appid={appid}")
                            raise RuntimeError("cancelled")
                logger.log(f"Download complete -> {dest_path}")

                if _is_download_cancelled(appid):
                    logger.log(f"Download marked cancelled after completion for appid={appid}")
                    raise RuntimeError("cancelled")

                try:
                    with open(dest_path, "rb") as fh:
                        magic = fh.read(4)
                        if magic not in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
                            file_size = os.path.getsize(dest_path)
                            with open(dest_path, "rb") as check_f:
                                preview = check_f.read(512)
                                content_preview = preview[:100].decode("utf-8", errors="ignore")
                            logger.warn(
                                f"API '{name}' returned non-zip (magic={magic.hex()}, size={file_size})"
                            )
                            if "Login required" in content_preview or "Sign in" in content_preview:
                                logger.error("Ryuu requested login. Cookie is invalid.")
                            try:
                                os.remove(dest_path)
                            except Exception:
                                pass
                            continue
                except FileNotFoundError:
                    logger.warn("Downloaded file not found after download")
                    continue
                except Exception as validation_exc:
                    logger.warn(f"File validation failed for API '{name}': {validation_exc}")
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                    continue

                try:
                    if _is_download_cancelled(appid):
                        logger.log(f"Processing cancelled for appid={appid}")
                        raise RuntimeError("cancelled")
                    _set_download_state(appid, {"status": "processing"})
                    _process_and_install_lua(appid, dest_path, destination_path)
                    if _is_download_cancelled(appid):
                        logger.log(f"Installation complete but cancelled for appid={appid}")
                        raise RuntimeError("cancelled")
                    try:
                        fetched_name = _fetch_app_name(appid) or f"UNKNOWN ({appid})"
                        _append_loaded_app(appid, fetched_name)
                        _log_appid_event(f"ADDED - {name}", appid, fetched_name)
                        _add_to_additional_apps(appid)
                    except Exception:
                        pass
                    _set_download_state(appid, {"status": "done", "success": True, "api": name})
                    return
                except Exception as install_exc:
                    if isinstance(install_exc, RuntimeError) and str(install_exc) == "cancelled":
                        try:
                            if os.path.exists(dest_path):
                                os.remove(dest_path)
                        except Exception:
                            pass
                        logger.log(f"Cancelled download cleanup complete for appid={appid}")
                        return
                    logger.warn(f"Processing failed -> {install_exc}")
                    _set_download_state(
                        appid, {"status": "failed", "error": f"Processing failed: {install_exc}"}
                    )
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                    return
        except RuntimeError as cancel_exc:
            if str(cancel_exc) == "cancelled":
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                except Exception:
                    pass
                logger.log(f"Download cancelled and cleaned up for appid={appid}")
                return
            logger.warn(f"Runtime error during download for appid={appid}: {cancel_exc}")
            _set_download_state(appid, {"status": "failed", "error": str(cancel_exc)})
            return
        except Exception as err:
            logger.warn(f"API '{name}' failed: {err}")
            continue

    _set_download_state(appid, {"status": "failed", "error": "Not available on any API"})

from .api_manifest import load_api_manifest

def start_add_via_luatools(appid: int, destination_path: str = "") -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})
    logger.log(f"StartAddViaLuaTools appid={appid} dest={destination_path or 'none'}")
    _set_download_state(appid, {"status": "queued", "bytesRead": 0, "totalBytes": 0})
    dp = destination_path.strip() or None
    thread = threading.Thread(target=_download_zip_for_app, args=(appid, dp), daemon=True)
    thread.start()
    return json.dumps({"success": True})

def get_add_status(appid: int) -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})
    state = _get_download_state(appid)
    return json.dumps({"success": True, "state": state})

def read_loaded_apps() -> str:
    try:
        path = _loaded_apps_path()
        entries = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle.read().splitlines():
                    if ":" in line:
                        appid_str, name = line.split(":", 1)
                        appid_str = appid_str.strip()
                        name = name.strip()
                        if appid_str.isdigit() and name:
                            entries.append({"appid": int(appid_str), "name": name})
        return json.dumps({"success": True, "apps": entries})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})

def dismiss_loaded_apps() -> str:
    try:
        path = _loaded_apps_path()
        if os.path.exists(path):
            os.remove(path)
        return json.dumps({"success": True})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})

def delete_luatools_for_app(appid: int) -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})
    base = detect_steam_install_path()
    target_dir = os.path.join(base or "", "config", "stplug-in")
    paths = [
        os.path.join(target_dir, f"{appid}.lua"),
        os.path.join(target_dir, f"{appid}.lua.disabled"),
    ]
    deleted = []
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                deleted.append(path)
        except Exception as exc:
            logger.warn(f"Failed to delete {path}: {exc}")
    try:
        name = _get_loaded_app_name(appid) or _fetch_app_name(appid) or f"UNKNOWN ({appid})"
        _remove_loaded_app(appid)
        if deleted:
            _log_appid_event("REMOVED", appid, name)
    except Exception:
        pass
    return json.dumps({"success": True, "deleted": deleted, "count": len(deleted)})

def get_icon_data_url() -> str:
    try:
        icon_path = public_path(WEB_UI_ICON_FILE)
        with open(icon_path, "rb") as handle:
            data = handle.read()
        b64 = base64.b64encode(data).decode("ascii")
        return json.dumps({"success": True, "dataUrl": f"data:image/png;base64,{b64}"})
    except Exception as exc:
        logger.warn(f"GetIconDataUrl failed: {exc}")
        return json.dumps({"success": False, "error": str(exc)})

def has_luatools_for_app(appid: int) -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})
    exists = has_lua_for_app(appid)
    return json.dumps({"success": True, "exists": exists})

def cancel_add_via_luatools(appid: int) -> str:
    try:
        appid = int(appid)
    except Exception:
        return json.dumps({"success": False, "error": "Invalid appid"})
    state = _get_download_state(appid)
    if not state or state.get("status") in {"done", "failed"}:
        return json.dumps({"success": True, "message": "Nothing to cancel"})
    _set_download_state(appid, {"status": "cancelled", "error": "Cancelled by user"})
    logger.log(f"Cancellation requested for appid={appid}")
    return json.dumps({"success": True})

def get_installed_lua_scripts() -> str:
    try:
        _preload_app_names_cache()
        base_path = detect_steam_install_path()
        if not base_path:
            return json.dumps({"success": False, "error": "Could not find Steam installation path"})
        target_dir = os.path.join(base_path, "config", "stplug-in")
        if not os.path.exists(target_dir):
            return json.dumps({"success": True, "scripts": []})
        installed_scripts = []
        try:
            for filename in os.listdir(target_dir):
                if filename.endswith(".lua") or filename.endswith(".lua.disabled"):
                    try:
                        appid_str = filename.replace(".lua.disabled", "").replace(".lua", "")
                        appid = int(appid_str)
                        is_disabled = filename.endswith(".lua.disabled")
                        game_name = ""
                        with APP_NAME_CACHE_LOCK:
                            game_name = APP_NAME_CACHE.get(appid, "")
                        if not game_name:
                            game_name = _get_loaded_app_name(appid)
                        if not game_name:
                            game_name = f"Unknown Game ({appid})"
                        file_path = os.path.join(target_dir, filename)
                        file_stat = os.stat(file_path)
                        file_size = file_stat.st_size
                        import datetime
                        modified_time = datetime.datetime.fromtimestamp(file_stat.st_mtime)
                        formatted_date = modified_time.strftime("%Y-%m-%d %H:%M:%S")
                        script_info = {
                            "appid": appid,
                            "gameName": game_name,
                            "filename": filename,
                            "isDisabled": is_disabled,
                            "fileSize": file_size,
                            "modifiedDate": formatted_date,
                            "path": file_path,
                        }
                        installed_scripts.append(script_info)
                    except ValueError:
                        continue
                    except Exception as exc:
                        logger.warn(f"Failed to process Lua file {filename}: {exc}")
                        continue
        except Exception as exc:
            logger.warn(f"Failed to scan stplug-in directory: {exc}")
            return json.dumps({"success": False, "error": f"Failed to scan directory: {str(exc)}"})
        installed_scripts.sort(key=lambda x: x["appid"])
        return json.dumps({"success": True, "scripts": installed_scripts})
    except Exception as exc:
        logger.warn(f"Failed to get installed Lua scripts: {exc}")
        return json.dumps({"success": False, "error": str(exc)})

def _get_launcher_path_file() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "data", "launcher_path.txt")

def load_launcher_path() -> str:
    try:
        path_file = _get_launcher_path_file()
        if os.path.exists(path_file):
            with open(path_file, "r", encoding="utf-8") as f:
                saved_path = f.read().strip()
                if saved_path and os.path.exists(saved_path):
                    return saved_path
    except Exception as e:
        logger.warn(f"Error reading launcher path: {e}")

    accela_appimage = os.path.expanduser("~/.local/share/ACCELA/ACCELA.AppImage")
    if os.path.exists(accela_appimage):
        return accela_appimage

    default_path = os.path.expanduser("~/.local/share/Bifrost/bin/Bifrost")
    return default_path

def save_launcher_path_config(path: str) -> str:
    try:
        path_file = _get_launcher_path_file()
        os.makedirs(os.path.dirname(path_file), exist_ok=True)
        clean_path = path.strip()
        with open(path_file, "w", encoding="utf-8") as f:
            f.write(clean_path)
        logger.log(f"Launcher path saved: {clean_path}")
        return json.dumps({"success": True, "path": clean_path})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def browse_for_launcher() -> str:
    try:
        cmd = [
            "zenity",
            "--file-selection",
            "--title=Select Launcher Executable",
            "--filename=" + os.path.expanduser("~/.local/share/"),
        ]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode == 0:
            selected_path = stdout.decode("utf-8").strip()
            return json.dumps({"success": True, "path": selected_path})
        else:
            return json.dumps({"success": False, "error": "No file selected or cancelled"})
    except Exception as e:
        logger.error(f"File picker error: {e}")
        return json.dumps({"success": False, "error": str(e)})


def _add_to_additional_apps(appid: int) -> None:
    try:
        config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
        if not os.path.exists(config_path):
            return
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        new_entry = f"  - {appid}"
        if new_entry in content:
            return
        lines = content.split('\n')
        insert_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith("AdditionalApps:"):
                insert_idx = i + 1
                break
        if insert_idx is None:
            return
        while insert_idx < len(lines) and lines[insert_idx].strip().startswith("- "):
            insert_idx += 1
        lines.insert(insert_idx, new_entry)
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        logger.log(f"Added {appid} to AdditionalApps")
    except Exception as e:
        logger.warn(f"Error adding to AdditionalApps: {e}")
