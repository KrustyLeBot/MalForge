"""Small network and storage helpers shared by the other modules."""

import json
import os
import urllib.request

from . import __version__

USER_AGENT = f"MalForge/{__version__}"


def app_data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "MalForge")
    os.makedirs(path, exist_ok=True)
    return path


def get_bytes(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url: str, timeout: int = 30):
    return json.loads(get_bytes(url, timeout).decode("utf-8"))


def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
