import os
import sys

def get_backend_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))

def get_plugin_dir() -> str:
    try:
        import decky
        return decky.DECKY_PLUGIN_DIR
    except Exception:
        backend_dir = get_backend_dir()
        return os.path.abspath(os.path.join(backend_dir, "..", ".."))

def get_data_dir() -> str:
    return os.path.join(get_plugin_dir(), "data")

def backend_path(filename: str) -> str:
    return os.path.join(get_backend_dir(), filename)

def public_path(filename: str) -> str:
    return os.path.join(get_plugin_dir(), "public", filename)
