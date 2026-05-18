from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .config import (
    API_JSON_FILE,
    API_MANIFEST_PROXY_URL,
    API_MANIFEST_URL,
    HTTP_PROXY_TIMEOUT_SECONDS,
)
from .http_client import ensure_http_client, get_http_client
from .logger import logger
from .utils import (
    backend_path,
    count_apis,
    normalize_manifest_text,
    read_text,
    write_text,
)

_APIS_INIT_DONE = False
_INIT_APIS_LAST_MESSAGE = ""


def init_apis(content_script_query: str = "") -> str:
    global _APIS_INIT_DONE, _INIT_APIS_LAST_MESSAGE
    logger.log("InitApis: invoked")
    if _APIS_INIT_DONE:
        logger.log("InitApis: already completed this session, skipping")
        return json.dumps({"success": True, "message": _INIT_APIS_LAST_MESSAGE})

    client = ensure_http_client("InitApis")
    api_json_path = backend_path(API_JSON_FILE)
    message = ""

    if os.path.exists(api_json_path):
        logger.log(f"InitApis: Local file exists -> {api_json_path}; skipping remote fetch")
    else:
        logger.log(f"InitApis: Local file not found -> {api_json_path}")
        manifest_text = ""
        try:
            try:
                logger.log(f"InitApis: Fetching manifest from {API_MANIFEST_URL}")
                resp = client.get(API_MANIFEST_URL)
                if resp.status_code == 200:
                    manifest_text = resp.text
                    logger.log("InitApis: Primary URL succeeded")
            except Exception as exc:
                logger.warn(f"InitApis: Primary URL failed: {exc}")

            if not manifest_text and API_MANIFEST_PROXY_URL:
                try:
                    logger.log(f"InitApis: Fetching manifest from proxy {API_MANIFEST_PROXY_URL}")
                    resp = client.get(
                        API_MANIFEST_PROXY_URL,
                        timeout=HTTP_PROXY_TIMEOUT_SECONDS,
                    )
                    if resp.status_code == 200:
                        manifest_text = resp.text
                        logger.log("InitApis: Proxy URL succeeded")
                except Exception as exc:
                    logger.warn(f"InitApis: Proxy URL failed: {exc}")

            if manifest_text:
                normalized = normalize_manifest_text(manifest_text)
                write_text(api_json_path, normalized)
                count = count_apis(normalized)
                message = f"Updated {count} APIs from GitHub."
                logger.log(f"InitApis: {message}")
            else:
                logger.warn("InitApis: No manifest data could be fetched")
                message = "No manifest data could be fetched."
        except Exception as exc:
            logger.warn(f"InitApis: fetch failed: {exc}")
            message = f"Failed to fetch API manifest: {exc}"

    if not _APIS_INIT_DONE:
        _APIS_INIT_DONE = True
        store_last_message(message)
    logger.log("InitApis: returning")
    return json.dumps({"success": True, "message": message})


def get_init_apis_message(content_script_query: str = "") -> str:
    return json.dumps({"success": True, "message": _INIT_APIS_LAST_MESSAGE})


def store_last_message(message: str) -> None:
    global _INIT_APIS_LAST_MESSAGE
    _INIT_APIS_LAST_MESSAGE = message


def fetch_free_apis_now(content_script_query: str = "") -> str:
    global _APIS_INIT_DONE, _INIT_APIS_LAST_MESSAGE
    logger.log("FetchFreeApisNow: forcing re-fetch")
    _APIS_INIT_DONE = False
    return init_apis(content_script_query)


def _load_user_apis() -> List[Dict[str, Any]]:
    try:
        from .downloads import load_user_apis as _load_user
        user = _load_user()
        return user.get("api_list", [])
    except Exception:
        return []

def _merge_api_lists(default_list: List[Dict[str, Any]], user_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    user_by_name = {}
    for api in user_list:
        name = api.get("name", "").lower()
        if name:
            user_by_name[name] = api
    merged = []
    seen_names = set()
    for api in user_list:
        name = api.get("name", "").lower()
        is_override = any(d.get("name", "").lower() == name for d in default_list)
        if not is_override:
            merged.append(api)
            seen_names.add(name)
    for api in default_list:
        name = api.get("name", "").lower()
        if name in user_by_name:
            merged.append(user_by_name.pop(name))
            seen_names.add(name)
        else:
            merged.append(api)
    for name, api in user_by_name.items():
        if name not in seen_names:
            merged.append(api)
    return [api for api in merged if api.get("enabled", True)]

def load_api_manifest() -> List[Dict[str, Any]]:
    api_json_path = backend_path(API_JSON_FILE)
    try:
        default_list: List[Dict[str, Any]] = []
        if os.path.exists(api_json_path):
            with open(api_json_path, "r", encoding="utf-8") as handle:
                root = json.load(handle)
            default_list = root.get("api_list", [])
            if not isinstance(default_list, list):
                default_list = []
        else:
            logger.warn("load_api_manifest: No API file found")
        user_list = _load_user_apis()
        return _merge_api_lists(default_list, user_list)
    except Exception as exc:
        logger.warn(f"load_api_manifest: {exc}")
    return []
