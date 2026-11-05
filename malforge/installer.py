"""Download, verify and install add-ons, and keep track of what was installed."""

import hashlib
import os
import shutil
import tempfile
import urllib.request
import zipfile

from . import curse, github, net
from .catalog import Catalog, Entry
from .wow import Flavor


class Manifest:
    """What MalForgé installed: key -> version and folders, per AddOns folder."""

    def __init__(self):
        self.path = os.path.join(net.app_data_dir(), "config.json")
        self.data = net.load_json(self.path, {})

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value
        net.save_json(self.path, self.data)

    def records(self, flavor: Flavor) -> dict:
        return self.data.setdefault("installed", {}).setdefault(flavor.addons_dir.lower(), {})

    def save(self) -> None:
        net.save_json(self.path, self.data)


def _safe_extract(archive: zipfile.ZipFile, target: str) -> list[str]:
    """Extract while refusing paths that escape the folder; returns the top-level folders."""
    root = os.path.realpath(target)
    tops = set()
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/") or ":" in name.split("/")[0]:
            raise OSError(f"Chemin suspect dans l'archive : {info.filename}")
        dest = os.path.realpath(os.path.join(target, name))
        if not (dest == root or dest.startswith(root + os.sep)):
            raise OSError(f"Chemin suspect dans l'archive : {info.filename}")
        parts = [p for p in name.split("/") if p]
        if len(parts) > 1 or info.is_dir():
            tops.add(parts[0])
    archive.extractall(target)
    return sorted(t for t in tops if os.path.isdir(os.path.join(target, t)))


def install(entry: Entry, flavor: Flavor, manifest: Manifest, progress=None) -> list[str]:
    """Install (or update) an add-on into the chosen WoW version; returns its folders."""
    size = 0
    if entry.source == "github":
        rel = github.latest_release(entry.repo, flavor.key)
        if rel is None:
            raise OSError("Ce dépôt GitHub ne publie aucun fichier .zip dans sa dernière release.")
        url, md5, version, size = rel.url, "", rel.tag, rel.size
    elif entry.source == "curse":
        cf = curse.latest_file(entry.uid, flavor.key)
        if cf is None:
            raise OSError("Aucun fichier compatible avec cette version du jeu.")
        url, md5, version, size = curse.download_url(cf), "", cf.name, cf.size
    else:
        detail = Catalog.details(entry.uid)
        url, md5 = detail.get("UIDownload"), str(detail.get("UIMD5", "")).lower()
        if not url:
            raise OSError("Aucun fichier à télécharger pour cet add-on.")
        version = str(detail.get("UIVersion", entry.version))

    addons = flavor.addons_dir
    os.makedirs(addons, exist_ok=True)
    work = tempfile.mkdtemp(prefix=".malforge-", dir=os.path.dirname(addons))  # same drive: moves are instant
    try:
        zpath = os.path.join(work, "addon.zip")
        req = urllib.request.Request(url, headers={"User-Agent": net.USER_AGENT})
        digest, done = hashlib.md5(), 0
        with urllib.request.urlopen(req, timeout=60) as resp, open(zpath, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            while True:
                chunk = resp.read(128 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if md5 and digest.hexdigest() != md5:
            raise OSError("Le fichier téléchargé est corrompu (MD5 différent).")
        if size and done != size:
            raise OSError(f"Téléchargement incomplet ({done} sur {size} octets).")

        extracted = os.path.join(work, "x")
        os.makedirs(extracted)
        with zipfile.ZipFile(zpath) as archive:
            folders = _safe_extract(archive, extracted)
        if not folders:
            raise OSError("L'archive ne contient aucun dossier d'add-on.")

        # Replace folders one by one; on failure the old ones are put back.
        backups = []
        try:
            for name in folders:
                dest = os.path.join(addons, name)
                if os.path.exists(dest):
                    bak = dest + ".mfbak"
                    shutil.rmtree(bak, ignore_errors=True)
                    os.replace(dest, bak)
                    backups.append((dest, bak))
                shutil.move(os.path.join(extracted, name), dest)
        except Exception:
            for dest, bak in backups:
                shutil.rmtree(dest, ignore_errors=True)
                os.replace(bak, dest)
            raise
        for _, bak in backups:
            shutil.rmtree(bak, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    manifest.records(flavor)[entry.key] = {"version": version, "folders": folders, "name": entry.name}
    manifest.save()
    return folders


def uninstall(key: str, folders: list[str], flavor: Flavor, manifest: Manifest) -> None:
    for name in folders:
        shutil.rmtree(os.path.join(flavor.addons_dir, name), ignore_errors=True)
    manifest.records(flavor).pop(key, None)
    manifest.save()
