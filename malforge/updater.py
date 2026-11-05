"""Self-update: read the latest GitHub release (published by the CI), verify its SHA-256 and replace the exe in place."""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass

from . import __version__, net

REPO = os.environ.get("MALFORGE_REPO", "KrustyLeBot/MalForge")
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
EXE_ASSET = "MalForge.exe"


@dataclass
class Release:
    version: str
    url: str
    sha256: str
    size: int
    notes: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    parts = []
    for piece in text.strip().lstrip("v").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts + [0] * (3 - len(parts)))


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse_version(remote) > parse_version(local)


def fetch_release(timeout: int = 15) -> Release:
    data = net.get_json(API_LATEST, timeout)
    asset = next(a for a in data["assets"] if a["name"] == EXE_ASSET)
    # GitHub publishes each file's SHA-256 ("sha256:..."); otherwise fall back to the CI's .sha256 asset.
    sha = str(asset.get("digest") or "").removeprefix("sha256:").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        side = next((a for a in data["assets"] if a["name"] == EXE_ASSET + ".sha256"), None)
        sha = net.get_bytes(side["browser_download_url"], timeout).decode().split()[0].lower() if side else ""
    return Release(str(data["tag_name"]).lstrip("v"), asset["browser_download_url"], sha,
                   int(asset.get("size", 0)), str(data.get("body") or ""))


def check() -> Release | None:
    """The latest release if it is newer than this build, else None."""
    release = fetch_release()
    return release if is_newer(release.version) else None


def running_exe() -> str | None:
    """Path of the running MalForge.exe, or None when running from source."""
    return sys.executable if getattr(sys, "frozen", False) else None


def download(release: Release, progress=None) -> str:
    exe = running_exe()
    # Same drive as the exe: os.replace cannot move a file across drives.
    folder = os.path.dirname(os.path.abspath(exe)) if exe else tempfile.gettempdir()
    target = os.path.join(folder, f"MalForge-{release.version}.exe.download")
    req = urllib.request.Request(release.url, headers={"User-Agent": net.USER_AGENT})
    digest, done = hashlib.sha256(), 0
    with urllib.request.urlopen(req, timeout=60) as resp, open(target, "wb") as out:
        total = int(resp.headers.get("Content-Length") or release.size or 0)
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    # A truncated or tampered download must never replace a working exe.
    if release.size and done != release.size:
        os.remove(target)
        raise OSError(f"Téléchargement incomplet ({done} sur {release.size} octets)")
    if release.sha256 and digest.hexdigest() != release.sha256:
        os.remove(target)
        raise OSError("Le fichier téléchargé ne correspond pas au SHA-256 publié")
    return target


def install(current_exe: str, new_file: str) -> str:
    """Replace the exe, even while it runs: Windows refuses to overwrite it but allows renaming it."""
    old = current_exe + ".old"
    if os.path.exists(old):
        os.remove(old)
    os.replace(current_exe, old)
    try:
        os.replace(new_file, current_exe)
    except OSError:
        os.replace(old, current_exe)
        raise
    return current_exe


def relaunch(exe: str) -> None:
    # A onefile exe started by another one inherits its bootloader variables and would look for its files in
    # the parent's temp folder, deleted when the parent exits; the reset makes it unpack its own.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([exe], creationflags=flags, close_fds=True, cwd=os.path.dirname(exe), env=env)


def cleanup_previous(exe: str | None = None) -> bool:
    """Remove the exe left behind by the last self-update; True once nothing is left."""
    exe = exe or running_exe()
    old = exe + ".old" if exe else ""
    if not old or not os.path.exists(old):
        return True
    try:
        os.remove(old)
        return True
    except OSError:
        return False
