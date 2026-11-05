"""CurseForge sans compte ni clé d'API.

- liste des fichiers d'un projet : l'API publique du site (par identifiant de projet) ;
- téléchargement : le CDN public de CurseForge ;
- infos (titre, description) et résolution d'un lien : cfwidget, un service communautaire gratuit.

La recherche par nom n'existe pas sans clé : on retrouve donc un add-on par son identifiant
(`## X-Curse-Project-ID` du .toc) ou par un lien de sa page.
"""

import re
import urllib.parse
from dataclasses import dataclass

from . import net
from .catalog import flavor_accepts

FILES_URL = "https://www.curseforge.com/api/v1/mods/{pid}/files"
WIDGET_URL = "https://api.cfwidget.com/{path}"
CDN_URL = "https://edge.forgecdn.net/files/{a}/{b}/{name}"
PAGE_URL = "https://www.curseforge.com/projects/{pid}"


@dataclass
class CurseFile:
    id: int
    name: str        # nom affiché, en général la version
    file_name: str
    size: int
    majors: list
    release: int     # 1 stable, 2 bêta, 3 alpha
    date: str


def _majors(versions) -> list[int]:
    out = []
    for v in versions or []:
        m = re.match(r"(\d+)\.", str(v))
        if m:
            out.append(int(m.group(1)))
    return out


def latest_file(pid: int, flavor_key: str) -> CurseFile | None:
    """Le fichier le plus récent compatible avec cette version du jeu (les stables d'abord)."""
    data = net.get_json(FILES_URL.format(pid=pid), 20).get("data") or []
    files = [CurseFile(int(f["id"]), str(f.get("displayName") or f["fileName"]), str(f["fileName"]),
                       int(f.get("fileLength") or 0), _majors(f.get("gameVersions")),
                       int(f.get("releaseType") or 1), str(f.get("dateCreated") or ""))
             for f in data if f.get("status", 4) == 4]
    files = [f for f in files if flavor_accepts(flavor_key, f.majors)]
    if not files:
        return None
    stable = [f for f in files if f.release == 1]
    return max(stable or files, key=lambda f: f.date)


def download_url(f: CurseFile) -> str:
    return CDN_URL.format(a=f.id // 1000, b=f.id % 1000, name=urllib.parse.quote(f.file_name))


def project_info(pid: int) -> dict:
    return net.get_json(WIDGET_URL.format(path=pid), 20)


def resolve(text: str) -> int:
    """Identifiant d'un projet à partir d'un nombre ou d'un lien de page CurseForge."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    m = re.search(r"curseforge\.com/wow/addons/([\w\-]+)", text)
    if not m:
        raise OSError("Lien CurseForge non reconnu (attendu : curseforge.com/wow/addons/nom).")
    return int(net.get_json(WIDGET_URL.format(path=f"wow/addons/{m.group(1)}"), 20)["id"])


def version_key(text: str) -> str:
    """Le numéro de version dans un libellé (« Auctionator 341 », « v0.5.0-forever » -> « 0.5.0 »)."""
    m = re.search(r"\d+(?:\.\d+)*", text or "")
    return m.group() if m else (text or "").strip().lower()
