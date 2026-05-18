from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser

from . import (
    api_manifest,
    auto_update,
    downloads,
    fixes,
    slssteam_config,
    steam_utils,
    linux_platform,
)
from .config import WEBKIT_DIR_NAME, WEB_UI_ICON_FILE, WEB_UI_JS_FILE
from .downloads import (
    cancel_add_via_luatools,
    delete_luatools_for_app,
    dismiss_loaded_apps,
    get_add_status,
    get_games_database,
    get_icon_data_url,
    get_installed_lua_scripts,
    get_steam_libraries,
    has_luatools_for_app,
    init_applist,
    init_games_db,
    read_loaded_apps,
    start_add_via_luatools,
    save_ryu_cookie,
    update_morrenus_key,
    save_launcher_path_config,
    load_launcher_path,
    browse_for_launcher,
)
from .fixes import (
    apply_game_fix,
    cancel_apply_fix,
    check_for_fixes,
    get_apply_fix_status,
    get_installed_fixes,
    get_unfix_status,
    unfix_game,
    apply_linux_native_fix,
)
from .http_client import close_http_client, ensure_http_client
from .logger import logger
from .paths import get_plugin_dir
from .settings.manager import (
    apply_settings_changes as _apply_settings,
    get_available_locales,
    get_settings_payload as _get_settings_payload,
    get_translation_map,
)
from .steam_utils import detect_steam_install_path, get_game_install_path_response, open_game_folder
from .utils import ensure_temp_download_dir


def _r(fn, *args, **kwargs):
    """Call a function that returns a JSON string and return the parsed dict."""
    result = fn(*args, **kwargs)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return {"success": True, "result": result}
    if isinstance(result, dict):
        return result
    return {"success": True, "result": result}


class Plugin:
    _http_initialized = False
    _background_done = False

    async def _main(self):
        logger.log("LuaTools Decky plugin starting...")

        try:
            detect_steam_install_path()
        except Exception as exc:
            logger.warn(f"Steam path detection failed: {exc}")

        try:
            ensure_http_client("LuaTools")
            self._http_initialized = True
        except Exception as exc:
            logger.error(f"HTTP client init failed: {exc}")

        ensure_temp_download_dir()

        def _background_init():
            try:
                init_applist()
            except Exception as exc:
                logger.warn(f"Applist: {exc}")

            try:
                init_games_db()
            except Exception as exc:
                logger.warn(f"Games DB: {exc}")

            try:
                result = api_manifest.init_apis("boot")
                logger.log(f"InitApis: {result}")
            except Exception as exc:
                logger.error(f"InitApis failed: {exc}")

            # Auto-update disabled for Decky: Millennium zips are incompatible
            self._background_done = True

        t = threading.Thread(target=_background_init, daemon=True, name="LuaTools-init")
        t.start()

    async def _unload(self):
        logger.log("LuaTools Decky unloading...")
        close_http_client("LuaTools")
        auto_update.stop_auto_update_background_check()

    async def _uninstall(self):
        logger.log("LuaTools Decky uninstalled")

    # --- FakeAppId management ---

    async def add_fake_app_id(self, appid: int) -> dict:
        return _r(self._add_fake_app_id_sync, appid)

    async def remove_fake_app_id(self, appid: int) -> dict:
        return _r(self._remove_fake_app_id_sync, appid)

    async def check_fake_app_id_status(self, appid: int) -> dict:
        return _r(self._check_fake_app_id_sync, appid)

    @staticmethod
    def _add_fake_app_id_sync(appid: int) -> str:
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            if not os.path.exists(config_path):
                try:
                    os.makedirs(os.path.dirname(config_path), exist_ok=True)
                    tmp_path = config_path + ".tmp"
                    with open(tmp_path, 'w') as f:
                        f.write("FakeAppIds:\n")
                    os.replace(tmp_path, config_path)
                except Exception:
                    return json.dumps({"success": False, "error": "Failed to create config.yaml"})

            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            entry_line = f"  {appid}: 480\n"
            for line in lines:
                if str(appid) in line and "480" in line:
                    return json.dumps({"success": True, "message": "FakeAppId is already configured!"})

            new_lines = []
            inserted = False
            has_tag = False

            for line in lines:
                new_lines.append(line)
                if line.strip().lower().startswith("fakeappids:"):
                    has_tag = True
                    new_lines.append(entry_line)
                    inserted = True

            if not has_tag:
                new_lines.append("\nFakeAppIds:\n")
                new_lines.append(entry_line)
            elif has_tag and not inserted:
                new_lines.append(entry_line)

            tmp_path = config_path + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            os.replace(tmp_path, config_path)

            logger.log(f"FakeAppId 480 added for {appid}")
            return json.dumps({"success": True, "message": "FakeAppId (480) added!"})
        except Exception as e:
            logger.error(f"FakeAppId Error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _remove_fake_app_id_sync(appid: int) -> str:
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            if not os.path.exists(config_path):
                return json.dumps({"success": True, "message": "Config not found."})
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            new_lines = []
            modified = False
            target_str = str(appid)
            for line in lines:
                stripped = line.strip()
                if (stripped.startswith(f"{target_str}:") or stripped.startswith(f"'{target_str}':") or stripped.startswith(f'"{target_str}":')) and "480" in stripped:
                    modified = True
                    continue
                new_lines.append(line)
            if modified:
                tmp_path = config_path + ".tmp"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                os.replace(tmp_path, config_path)
            return json.dumps({"success": True, "message": "FakeAppId removed."})
        except Exception as e:
            logger.warn(f"Error removing FakeAppId: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _check_fake_app_id_sync(appid: int) -> str:
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            if not os.path.exists(config_path):
                return json.dumps({"success": True, "exists": False})
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if f"  {appid}: 480" in content:
                return json.dumps({"success": True, "exists": True})
            return json.dumps({"success": True, "exists": False})
        except Exception:
            return json.dumps({"success": True, "exists": False})

    # --- Game Token management ---

    async def add_game_token(self, appid: int) -> dict:
        return _r(self._add_game_token_sync, appid)

    async def remove_game_token(self, appid: int) -> dict:
        return _r(self._remove_game_token_sync, appid)

    async def check_game_token_status(self, appid: int) -> dict:
        return _r(self._check_game_token_sync, appid)

    @staticmethod
    def _add_game_token_sync(appid: int) -> str:
        try:
            plugin_root = get_plugin_dir()
            json_path = os.path.join(plugin_root, "data", "appaccesstokens.json")
            if not os.path.exists(json_path):
                return json.dumps({"success": False, "error": "appaccesstokens.json not found."})
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            if not os.path.exists(config_path):
                tmp_path = config_path + ".tmp"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    f.write("AppTokens:\n")
                os.replace(tmp_path, config_path)
            with open(json_path, 'r', encoding='utf-8') as f:
                tokens_db = json.load(f)
            token = tokens_db.get(str(appid))
            if not token:
                return json.dumps({"success": False, "error": f"Token not found for AppID {appid}."})
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            entry = f"{appid}: {token}"
            for line in lines:
                if str(appid) in line and token in line:
                    return json.dumps({"success": True, "message": "Token already in config.yaml."})
            new_lines = []
            inserted = False
            has_tag = False
            for line in lines:
                new_lines.append(line)
                if line.strip().startswith("AppTokens:"):
                    has_tag = True
                    new_lines.append(f"  {entry}\n")
                    inserted = True
            if not has_tag:
                new_lines.append("\nAppTokens:\n")
                new_lines.append(f"  {entry}\n")
            elif has_tag and not inserted:
                new_lines.append(f"  {entry}\n")
            tmp_path = config_path + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            os.replace(tmp_path, config_path)
            return json.dumps({"success": True, "message": "Token added!"})
        except Exception as e:
            logger.error(f"Token Error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _remove_game_token_sync(appid: int) -> str:
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            if not os.path.exists(config_path):
                return json.dumps({"success": True, "message": "Config not found."})
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            new_lines = []
            token_removed = False
            target_id_str = str(appid)
            for line in lines:
                stripped = line.strip()
                if (stripped.startswith(f"{target_id_str}:") or
                    stripped.startswith(f"'{target_id_str}':") or
                    stripped.startswith(f'"{target_id_str}":')):
                    token_removed = True
                    continue
                new_lines.append(line)
            if token_removed:
                tmp_path = config_path + ".tmp"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                os.replace(tmp_path, config_path)
            return json.dumps({"success": True, "message": "Token removed."})
        except Exception as e:
            logger.warn(f"Error removing token: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _check_game_token_sync(appid: int) -> str:
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            if not os.path.exists(config_path):
                return json.dumps({"success": True, "exists": False})
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            in_tokens = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("AppTokens:"):
                    in_tokens = True
                    continue
                if in_tokens:
                    indent = len(line) - len(line.lstrip())
                    if indent <= 2 and stripped and not stripped.startswith("#"):
                        in_tokens = False
                    elif stripped.startswith(f"{appid}:"):
                        return json.dumps({"success": True, "exists": True})
            return json.dumps({"success": True, "exists": False})
        except Exception:
            return json.dumps({"success": True, "exists": False})

    # --- DLC management ---

    async def add_game_dlcs(self, appid: int) -> dict:
        return _r(self._add_game_dlcs_sync, appid)

    async def remove_game_dlcs(self, appid: int) -> dict:
        return _r(self._remove_game_dlcs_sync, appid)

    async def check_game_dlcs_status(self, appid: int) -> dict:
        return _r(self._check_game_dlcs_sync, appid)

    @staticmethod
    def _fetch_dlc_list(appid: int):
        try:
            client = ensure_http_client("DLC Fetcher")
            url_list = f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic,dlc"
            resp = client.get(url_list, timeout=10)
            data = resp.json()
            if not data or str(appid) not in data or not data[str(appid)]['success']:
                return []
            game_data = data[str(appid)]['data']
            dlc_ids = game_data.get('dlc', [])
            if not dlc_ids:
                return []
            dlc_info = []
            chunk_size = 10
            for i in range(0, len(dlc_ids), chunk_size):
                chunk = dlc_ids[i:i + chunk_size]
                ids_str = ",".join(map(str, chunk))
                try:
                    url_names = f"https://store.steampowered.com/api/appdetails?appids={ids_str}&filters=basic"
                    resp_names = client.get(url_names, timeout=10)
                    names_data = resp_names.json()
                    for d_id in chunk:
                        d_id_str = str(d_id)
                        name = f"DLC {d_id}"
                        if names_data and d_id_str in names_data and names_data[d_id_str]['success']:
                            name = names_data[d_id_str]['data']['name']
                        name = name.replace('"', '').replace("'", "")
                        dlc_info.append((d_id, name))
                except Exception:
                    for d_id in chunk:
                        dlc_info.append((d_id, f"DLC {d_id}"))
            return dlc_info
        except Exception as e:
            logger.error(f"Error fetching DLCs: {e}")
            return []

    @staticmethod
    def _add_game_dlcs_sync(appid: int) -> str:
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            if not os.path.exists(config_path):
                return json.dumps({"success": False, "error": "SLSsteam config not found."})
            dlcs = Plugin._fetch_dlc_list(appid)
            if not dlcs:
                return json.dumps({"success": False, "error": "No DLCs found on Steam."})
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            in_dlc_data = False
            for line in lines:
                if line.strip().startswith("DlcData:"):
                    in_dlc_data = True
                if in_dlc_data and line.strip().startswith(f"{appid}:"):
                    return json.dumps({"success": True, "message": "DLCs already configured!"})
            new_block = []
            new_block.append(f"  {appid}:\n")
            for d_id, d_name in dlcs:
                new_block.append(f"    {d_id}: \"{d_name}\"\n")
            new_lines = []
            inserted = False
            has_tag = False
            for line in lines:
                new_lines.append(line)
                if line.strip().startswith("DlcData:"):
                    has_tag = True
                    new_lines.extend(new_block)
                    inserted = True
            if not has_tag:
                new_lines.append("\nDlcData:\n")
                new_lines.extend(new_block)
            tmp_path = config_path + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            os.replace(tmp_path, config_path)
            return json.dumps({"success": True, "message": f"{len(dlcs)} DLCs added!"})
        except Exception as e:
            logger.error(f"Add DLC Error: {e}")
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _remove_game_dlcs_sync(appid: int) -> str:
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            if not os.path.exists(config_path):
                return json.dumps({"success": True})
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            new_lines = []
            in_target_block = False
            target_str = f"{appid}:"
            found = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(target_str):
                    in_target_block = True
                    found = True
                    continue
                if in_target_block:
                    indent = len(line) - len(line.lstrip())
                    if indent <= 2 and stripped:
                        in_target_block = False
                        new_lines.append(line)
                    else:
                        continue
                else:
                    new_lines.append(line)
            tmp_path = config_path + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            os.replace(tmp_path, config_path)
            return json.dumps({"success": True, "message": "DLCs removed from config."})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    @staticmethod
    def _check_game_dlcs_sync(appid: int) -> str:
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            if not os.path.exists(config_path):
                return json.dumps({"success": True, "exists": False})
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if f"\n  {appid}:" in content or f"  {appid}:" in content:
                return json.dumps({"success": True, "exists": True})
            return json.dumps({"success": True, "exists": False})
        except Exception:
            return json.dumps({"success": True, "exists": False})

    # --- SLSsteam Engine Core ---

    async def get_sls_play_status(self) -> dict:
        enabled = slssteam_config.is_play_not_owned_enabled()
        return {"success": True, "enabled": enabled}

    async def set_sls_play_status(self, enabled: bool) -> dict:
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            lines: list[str] = []
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            new_val = "yes" if enabled else "no"
            new_lines: list[str] = []
            found_play = False
            for line in lines:
                if line.strip().lower().startswith("playnotownedgames:"):
                    new_lines.append(f"PlayNotOwnedGames: {new_val}\n")
                    found_play = True
                elif line.strip().lower().startswith("notifications:"):
                    new_lines.append("Notifications: no\n")
                else:
                    new_lines.append(line)
            if not found_play:
                new_lines.append(f"PlayNotOwnedGames: {new_val}\n")
            tmp_path = config_path + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            os.replace(tmp_path, config_path)
            return {"success": True}
        except Exception as e:
            logger.error(f"Error saving SLSsteam config: {e}")
            return {"success": False, "error": str(e)}

    async def get_slssteam_status(self) -> dict:
        return {
            "success": True,
            "installed": linux_platform.check_slssteam_installed(),
            "injected": linux_platform.verify_slssteam_injected(),
            "config_exists": slssteam_config.config_exists(),
        }

    # --- ACCELA / Launcher ---

    async def get_launcher_path(self) -> dict:
        path = load_launcher_path()
        accela_default = os.path.expanduser("~/.local/share/ACCELA/run.sh")
        if not path or "Bifrost" in path or not os.path.exists(path):
            path = accela_default if os.path.exists(accela_default) else "/home/deck/.local/share/ACCELA/run.sh"
        return {"success": True, "path": path}

    async def save_launcher_path(self, path: str) -> dict:
        return _r(save_launcher_path_config, path)

    async def browse_for_launcher(self) -> dict:
        return _r(browse_for_launcher)

    async def check_accela_installed(self) -> dict:
        return {"success": True, "installed": linux_platform.check_accela_installed()}

    # --- Game Downloads ---

    async def start_add_via_luatools(self, appid: int, destination_path: str = "") -> dict:
        return _r(start_add_via_luatools, appid, destination_path)

    async def get_steam_libraries(self) -> dict:
        return _r(get_steam_libraries)

    async def get_add_status(self, appid: int) -> dict:
        return _r(get_add_status, appid)

    async def cancel_add_via_luatools(self, appid: int) -> dict:
        return _r(cancel_add_via_luatools, appid)

    async def has_luatools_for_app(self, appid: int) -> dict:
        return _r(has_luatools_for_app, appid)

    async def delete_luatools_for_app(self, appid: int) -> dict:
        return _r(delete_luatools_for_app, appid)

    async def read_loaded_apps(self) -> dict:
        return _r(read_loaded_apps)

    async def dismiss_loaded_apps(self) -> dict:
        return _r(dismiss_loaded_apps)

    async def get_installed_lua_scripts(self) -> dict:
        return _r(get_installed_lua_scripts)

    async def get_games_database(self) -> dict:
        return _r(get_games_database)

    async def get_icon_data_url(self) -> dict:
        return _r(get_icon_data_url)

    # --- Game Fixes ---

    async def check_for_fixes(self, appid: int) -> dict:
        return _r(check_for_fixes, appid)

    async def apply_game_fix(self, appid: int, download_url: str, install_path: str, fix_type: str = "", game_name: str = "") -> dict:
        return _r(apply_game_fix, appid, download_url, install_path, fix_type, game_name)

    async def get_apply_fix_status(self, appid: int) -> dict:
        return _r(get_apply_fix_status, appid)

    async def cancel_apply_fix(self, appid: int) -> dict:
        return _r(cancel_apply_fix, appid)

    async def unfix_game(self, appid: int, install_path: str = "", fix_date: str = "") -> dict:
        return _r(unfix_game, appid, install_path, fix_date)

    async def get_unfix_status(self, appid: int) -> dict:
        return _r(get_unfix_status, appid)

    async def get_installed_fixes(self) -> dict:
        return _r(get_installed_fixes)

    async def apply_linux_native_fix(self, install_path: str) -> dict:
        return _r(apply_linux_native_fix, install_path)

    # --- Steam / Game Path ---

    async def get_game_install_path(self, appid: int) -> dict:
        return _r(get_game_install_path_response, appid)

    async def open_game_folder(self, path: str) -> dict:
        success = open_game_folder(path)
        return {"success": success}

    async def check_game_update(self, appid: int) -> dict:
        return _r(self._check_game_update_sync, appid)

    @staticmethod
    def _check_game_update_sync(appid: int) -> str:
        try:
            accela_path = load_launcher_path()
            if not accela_path or not os.path.exists(accela_path):
                default_accela = os.path.expanduser("~/.local/share/ACCELA/run.sh")
                if os.path.exists(default_accela):
                    accela_path = default_accela
                else:
                    return json.dumps({"success": False, "status": "Launcher Config Missing", "color": "#FF5252"})
            if os.path.isfile(accela_path):
                accela_path = os.path.dirname(accela_path)
            depots_dir = os.path.join(accela_path, "depots")
            depot_file = os.path.join(depots_dir, f"{appid}.depot")
            logger.log(f"Checking depot file: {depot_file}")
            if not os.path.exists(depot_file):
                return json.dumps({"success": True, "status": "Not Managed by ACCELA", "color": "#777"})
            local_manifest = ""
            local_depot_id = ""
            try:
                with open(depot_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    parts = content.split(':')
                    if len(parts) >= 2:
                        local_manifest = parts[-1].strip()
                        raw_depot = parts[-2]
                        local_depot_id = "".join(filter(str.isdigit, raw_depot))
            except Exception:
                return json.dumps({"success": False, "status": "Read Error", "color": "#FF5252"})
            if not local_manifest or not local_depot_id:
                return json.dumps({"success": False, "status": "Invalid Depot File", "color": "#FF5252"})
            client = ensure_http_client("Update Checker")
            url = f"https://api.steamcmd.net/v1/info/{appid}"
            resp = client.get(url, timeout=5)
            if resp.status_code != 200:
                return json.dumps({"success": False, "status": "API Error", "color": "#FF5252"})
            data = resp.json()
            if data.get('status') != 'success':
                return json.dumps({"success": False, "status": "API Failed", "color": "#FF5252"})
            app_data = data['data'].get(str(appid), {})
            depots_data = app_data.get('depots', {})
            if local_depot_id in depots_data:
                manifests = depots_data[local_depot_id].get('manifests', {})
                if 'public' in manifests:
                    remote_manifest = manifests['public'].get('gid')
                    if str(local_manifest) == str(remote_manifest):
                        return json.dumps({"success": True, "status": "Up to Date", "color": "#4CAF50"})
                    else:
                        return json.dumps({"success": True, "status": "Update Available", "color": "#00FF00"})
            return json.dumps({"success": True, "status": "Unknown Version", "color": "#FF5252"})
        except Exception as e:
            logger.error(f"Update Check Error: {e}")
            return json.dumps({"success": False, "status": "Error", "color": "#FF5252"})

    # --- API Keys & Cookies ---

    async def save_ryu_cookie(self, cookie: str) -> dict:
        return _r(save_ryu_cookie, cookie)

    async def update_morrenus_key(self, key: str) -> dict:
        return _r(update_morrenus_key, key)

    # --- Settings ---

    async def get_settings_config(self) -> dict:
        try:
            payload = _get_settings_payload()
            return {
                "success": True,
                "schemaVersion": payload.get("version"),
                "schema": payload.get("schema", []),
                "values": payload.get("values", {}),
                "language": payload.get("language"),
                "locales": payload.get("locales", []),
                "translations": payload.get("translations", {}),
            }
        except Exception as exc:
            logger.warn(f"GetSettingsConfig failed: {exc}")
            return {"success": False, "error": str(exc)}

    async def apply_settings_changes(self, changes: dict) -> dict:
        return _r(_apply_settings, changes)

    async def get_available_locales(self) -> dict:
        locales = get_available_locales()
        return {"success": True, "locales": locales}

    async def get_translations(self, language: str = "en") -> dict:
        bundle = get_translation_map(language)
        bundle["success"] = True
        return bundle

    # --- URLs & external ---

    async def open_external_url(self, url: str) -> dict:
        try:
            value = str(url or "").strip()
            if not (value.startswith("http://") or value.startswith("https://")):
                return {"success": False, "error": "Invalid URL"}
            webbrowser.open(value)
            return {"success": True}
        except Exception as exc:
            logger.warn(f"OpenExternalUrl failed: {exc}")
            return {"success": False, "error": str(exc)}

    # --- ProtoDB ---

    async def get_proton_db_status(self, appid: int) -> dict:
        try:
            url = f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json"
            client = ensure_http_client("ProtonDB")
            resp = client.get(url, timeout=3)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            elif resp.status_code == 404:
                return {"success": False, "error": "Not Found"}
            else:
                return {"success": False, "error": f"Status {resp.status_code}"}
        except Exception as e:
            logger.warn(f"ProtonDB fetch failed for {appid}: {e}")
            return {"success": False, "error": str(e)}

    # --- Full Uninstall ---

    async def uninstall_game_full(self, appid: int) -> dict:
        return _r(self._uninstall_game_full_sync, appid)

    @staticmethod
    def _remove_from_additional_apps(appid: int):
        try:
            config_path = os.path.expanduser("~/.config/SLSsteam/config.yaml")
            if not os.path.exists(config_path):
                return
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            new_lines = []
            modified = False
            target_str = f"- {appid}"
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(target_str):
                    remainder = stripped[len(target_str):]
                    if not remainder or remainder[0] in " \t#":
                        modified = True
                        continue
                new_lines.append(line)
            if modified:
                tmp_path = config_path + ".tmp"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                os.replace(tmp_path, config_path)
        except Exception as e:
            logger.warn(f"Error removing from AdditionalApps: {e}")

    @staticmethod
    def _uninstall_game_full_sync(appid: int) -> str:
        import shutil
        try:
            path_info = get_game_install_path_response(appid)
            install_path = path_info.get("installPath") if isinstance(path_info, dict) else None
            if install_path and os.path.exists(install_path):
                shutil.rmtree(install_path, ignore_errors=True)
                steamapps_dir = os.path.dirname(os.path.dirname(install_path))
                acf_file = os.path.join(steamapps_dir, f"appmanifest_{appid}.acf")
                if os.path.exists(acf_file):
                    os.remove(acf_file)
            delete_luatools_for_app(appid)
            Plugin._remove_from_additional_apps(appid)
            return json.dumps({"success": True})
        except Exception as e:
            logger.error(f"Error uninstalling game: {e}")
            return json.dumps({"success": False, "error": str(e)})

    # --- Workshop ---

    async def start_workshop_download(self, appid: int, pubfile_id: int) -> dict:
        return _r(self._start_workshop_download_sync, appid, pubfile_id)

    async def get_workshop_download_status(self) -> dict:
        return _r(self._get_workshop_status_sync)

    async def cancel_workshop_download(self) -> dict:
        return _r(self._cancel_workshop_sync)

    _workshop_state = {
        "status": "idle",
        "progress": 0.0,
        "message": "",
        "download_path": "",
        "process": None,
    }

    @staticmethod
    def _start_workshop_download_sync(appid: int, pubfile_id: int) -> str:
        import stat as stat_mod
        global _workshop_state
        ws = Plugin._workshop_state
        if ws["status"] == "downloading":
            return json.dumps({"success": False, "error": "Download already in progress."})

        steam_root = detect_steam_install_path()
        if not steam_root:
            return json.dumps({"success": False, "error": "Steam path not found"})
        download_dir = os.path.join(steam_root, "steamapps", "workshop", "content", str(appid), str(pubfile_id))
        try:
            if not os.path.exists(download_dir):
                os.makedirs(download_dir, exist_ok=True)
        except Exception as e:
            return json.dumps({"success": False, "error": f"Failed to create dir: {e}"})

        ws.update({
            "status": "downloading",
            "progress": 0,
            "message": "Initializing...",
            "download_path": download_dir,
            "process": None,
            "appid": appid,
            "pubfile_id": pubfile_id,
        })

        exe_path = Plugin._find_depot_downloader()
        if not exe_path:
            ws.update({"status": "failed", "message": "DepotDownloader not found"})
            return json.dumps({"success": False, "error": "DepotDownloader not found"})

        if os.path.isfile(exe_path):
            exe_dir = os.path.dirname(exe_path)
        else:
            exe_dir = exe_path

        import subprocess as sp
        cmd = [
            os.path.join(exe_dir, "DepotDownloaderMod") if os.path.isdir(exe_dir) else exe_path,
            "-app", str(appid),
            "-pubfile", str(pubfile_id),
            "-dir", download_dir,
            "-max-downloads", "8",
        ]

        try:
            st = os.stat(cmd[0])
            os.chmod(cmd[0], st.st_mode | stat_mod.S_IEXEC)
        except Exception:
            pass

        def _run():
            ws = Plugin._workshop_state
            try:
                process = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.STDOUT, text=True, encoding='utf-8', errors='replace')
                ws["process"] = process
                percent_regex = __import__('re').compile(r"(\d{1,3}\.\d{2})%")
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        clean = line.strip()
                        if clean:
                            ws["message"] = clean
                        m = percent_regex.search(clean)
                        if m:
                            ws["progress"] = float(m.group(1))
                rc = process.poll()
                ws["process"] = None
                ws["status"] = "done" if rc == 0 else "failed"
                ws["message"] = "Download Complete!" if rc == 0 else f"Error code: {rc}"
                ws["progress"] = 100.0 if rc == 0 else ws["progress"]
            except Exception as e:
                ws["status"] = "failed"
                ws["message"] = str(e)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return json.dumps({"success": True, "message": "Download started"})

    @staticmethod
    def _get_workshop_status_sync() -> str:
        ws = Plugin._workshop_state.copy()
        ws.pop("process", None)
        return json.dumps(ws)

    @staticmethod
    def _cancel_workshop_sync() -> str:
        ws = Plugin._workshop_state
        if ws.get("process"):
            try:
                ws["process"].kill()
            except Exception:
                pass
        ws["status"] = "cancelled"
        ws["message"] = "Cancelled by user."
        return json.dumps({"success": True})

    @staticmethod
    def _find_depot_downloader() -> str:
        custom_path = ""
        try:
            from .downloads import _get_launcher_path_file
            path_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "workshop_path.txt")
            if os.path.exists(path_file):
                with open(path_file, "r") as f:
                    custom_path = f.read().strip()
        except Exception:
            pass

        if custom_path and os.path.exists(custom_path):
            if os.path.isdir(custom_path):
                exe = os.path.join(custom_path, "DepotDownloaderMod")
                if os.path.exists(exe):
                    return exe
            else:
                return custom_path

        base_path = get_plugin_dir()
        exe = os.path.join(base_path, "DepotDownloaderMod")
        if os.path.exists(exe):
            return exe
        return ""

    async def save_workshop_tool_path(self, path: str) -> dict:
        try:
            ws_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "workshop_path.txt")
            os.makedirs(os.path.dirname(ws_path), exist_ok=True)
            with open(ws_path, "w", encoding="utf-8") as f:
                f.write(path.strip())
            return {"success": True, "message": "Path saved"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_workshop_tool_path(self) -> dict:
        try:
            ws_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "workshop_path.txt")
            path = ""
            if os.path.exists(ws_path):
                with open(ws_path, "r") as f:
                    path = f.read().strip()
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Platform diagnostics ---

    async def get_platform_summary(self) -> dict:
        return linux_platform.get_platform_summary()

    async def verify_slssteam_injected(self) -> dict:
        return linux_platform.verify_slssteam_injected()

    async def init_apis(self) -> dict:
        return _r(api_manifest.init_apis, "")

    async def check_for_updates_now(self) -> dict:
        return auto_update.check_for_updates_now()

    async def restart_steam(self) -> dict:
        try:
            ok = auto_update.restart_steam()
            return {"success": ok, "message": "Restarting Steam..." if ok else "Failed to restart Steam"}
        except Exception as e:
            return {"success": False, "error": str(e)}
