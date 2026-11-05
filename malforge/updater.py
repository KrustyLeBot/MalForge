"""Auto-mise à jour : lit la dernière release GitHub (publiée par la CI), vérifie le SHA-256 et remplace l'exe en place."""

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
    # GitHub publie le SHA-256 de chaque fichier ("sha256:...") ; sinon on retombe sur l'asset .sha256 de la CI.
    sha = str(asset.get("digest") or "").removeprefix("sha256:").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        side = next((a for a in data["assets"] if a["name"] == EXE_ASSET + ".sha256"), None)
        sha = net.get_bytes(side["browser_download_url"], timeout).decode().split()[0].lower() if side else ""
    return Release(str(data["tag_name"]).lstrip("v"), asset["browser_download_url"], sha,
                   int(asset.get("size", 0)), str(data.get("body") or ""))


def check() -> Release | None:
    """La dernière release si elle est plus récente que cette version, sinon None."""
    release = fetch_release()
    return release if is_newer(release.version) else None


def running_exe() -> str | None:
    """Chemin de MalForge.exe en cours d'exécution, ou None depuis les sources."""
    return sys.executable if getattr(sys, "frozen", False) else None


def download(release: Release, progress=None) -> str:
    exe = running_exe()
    # Même disque que l'exe : os.replace ne sait pas changer de lecteur.
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
    # Un téléchargement tronqué ou modifié ne doit jamais remplacer un exe qui marche.
    if release.size and done != release.size:
        os.remove(target)
        raise OSError(f"Téléchargement incomplet ({done} sur {release.size} octets)")
    if release.sha256 and digest.hexdigest() != release.sha256:
        os.remove(target)
        raise OSError("Le fichier téléchargé ne correspond pas au SHA-256 publié")
    return target


def install(current_exe: str, new_file: str) -> str:
    """Remplace l'exe (même en cours d'exécution) : Windows interdit l'écrasement mais autorise le renommage."""
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
    # Un exe onefile lancé par un autre hérite des variables du bootloader et chercherait ses fichiers dans
    # le dossier temporaire du parent, supprimé à sa sortie ; la remise à zéro force sa propre extraction.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([exe], creationflags=flags, close_fds=True, cwd=os.path.dirname(exe), env=env)


def cleanup_previous(exe: str | None = None) -> bool:
    """Supprime l'ancien exe laissé par la dernière mise à jour ; True quand il ne reste plus rien."""
    exe = exe or running_exe()
    old = exe + ".old" if exe else ""
    if not old or not os.path.exists(old):
        return True
    try:
        os.remove(old)
        return True
    except OSError:
        return False
