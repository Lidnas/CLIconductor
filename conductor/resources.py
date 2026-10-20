import os
import sys


def resource_path(relative: str) -> str:
    """Resolve a resource path that works both in dev and frozen (PyInstaller) builds."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def data_dir() -> str:
    """Writable user data directory (config/state)."""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        localapp = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        cfg = os.path.join(appdata, "CLIConductor")
        state = os.path.join(localapp, "CLIConductor")
    else:
        cfg = os.path.join(os.path.expanduser("~"), ".config", "CLIConductor")
        state = os.path.join(os.path.expanduser("~"), ".local", "share", "CLIConductor")
    os.makedirs(cfg, exist_ok=True)
    os.makedirs(state, exist_ok=True)
    return cfg, state