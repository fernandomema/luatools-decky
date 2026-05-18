from typing import Optional

import httpx

from .config import HTTP_TIMEOUT_SECONDS
from .logger import logger

_HTTP_CLIENT: Optional[httpx.Client] = None

def ensure_http_client(context: str = "") -> httpx.Client:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        prefix = f"{context}: " if context else ""
        logger.log(f"{prefix}Initializing shared HTTPX client...")
        try:
            _HTTP_CLIENT = httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
            logger.log(f"{prefix}HTTPX client initialized")
        except Exception as exc:
            logger.error(f"{prefix}Failed to initialize HTTPX client: {exc}")
            raise
    return _HTTP_CLIENT

def get_http_client() -> httpx.Client:
    return ensure_http_client()

def close_http_client(context: str = "") -> None:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        return
    try:
        _HTTP_CLIENT.close()
    except Exception:
        pass
    finally:
        _HTTP_CLIENT = None
        prefix = f"{context}: " if context else ""
        logger.log(f"{prefix}HTTPX client closed")
