"""CurseForge without an account or API key.

- file list of a project: the website's public API, by project id;
- download: CurseForge's public CDN;
- project info (title, description) and link resolution: cfwidget, a free community service.

Searching by name is not possible without a key, so an add-on is found by its project id
(`## X-Curse-Project-ID` in the .toc) or by a link to its page. With a free API key from
console.curseforge.com the official search endpoint is used as well.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
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
    name: str        # display name, usually the version
    file_name: str
    size: int
    majors: list
    release: int     # 1 stable, 2 beta, 3 alpha
    date: str


def _majors(versions) -> list[int]:
    out = []
    for v in versions or []:
        m = re.match(r"(\d+)\.", str(v))
        if m:
            out.append(int(m.group(1)))
    return out


def latest_file(pid: int, flavor_key: str) -> CurseFile | None:
    """The newest file compatible with this game version (stable releases first)."""
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


SEARCH_URL = "https://api.curseforge.com/v1/mods/search?"


def search(api_key: str, text: str, limit: int = 30) -> list:
    """Search by name through the official API (free key, https://console.curseforge.com). Returns raw dicts."""
    query = urllib.parse.urlencode({"gameId": 1, "searchFilter": text, "pageSize": limit,
                                    "sortField": 2, "sortOrder": "desc"})
    req = urllib.request.Request(SEARCH_URL + query, headers={"x-api-key": api_key, "Accept": "application/json",
                                                              "User-Agent": net.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8")).get("data") or []
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise OSError("Clé CurseForge refusée : vérifie qu'elle est bien copiée en entier.") from exc
        raise


def download_url(f: CurseFile) -> str:
    return CDN_URL.format(a=f.id // 1000, b=f.id % 1000, name=urllib.parse.quote(f.file_name))


def project_info(pid: int) -> dict:
    return net.get_json(WIDGET_URL.format(path=pid), 20)


def resolve(text: str) -> int:
    """Project id from a number or from a CurseForge page link."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    m = re.search(r"curseforge\.com/wow/addons/([\w\-]+)", text)
    if not m:
        raise OSError("Lien CurseForge non reconnu (attendu : curseforge.com/wow/addons/nom).")
    return int(net.get_json(WIDGET_URL.format(path=f"wow/addons/{m.group(1)}"), 20)["id"])


def version_key(text: str) -> str:
    """The version number inside a label ("Auctionator 341", "v0.5.0-forever" -> "0.5.0")."""
    m = re.search(r"\d+(?:\.\d+)*", text or "")
    return m.group() if m else (text or "").strip().lower()
