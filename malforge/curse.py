"""CurseForge without an account or API key.

- search by name, lookup by page slug, project info and description: api.curse.tools, a free public relay of the
  official CurseForge API (CurseForge's own API needs a key, and some keys are refused for search);
- file list of a project: the CurseForge website's public API, by project id;
- download: CurseForge's public CDN;
- fallback when the relay is down: cfwidget, a free community service, with page slugs guessed from the typed name.
"""

import re
import unicodedata
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import net
from .catalog import flavor_accepts

RELAY = "https://api.curse.tools/v1/cf/"
FILES_URL = "https://www.curseforge.com/api/v1/mods/{pid}/files"
WIDGET_URL = "https://api.cfwidget.com/{path}"
CDN_URL = "https://edge.forgecdn.net/files/{a}/{b}/{name}"
PAGE_URL = "https://www.curseforge.com/projects/{pid}"
SLUG_RE = re.compile(r"curseforge\.com/wow/addons/([\w\-]+)")


@dataclass
class CurseFile:
    id: int
    name: str        # display name, usually the version
    file_name: str
    size: int
    majors: list
    release: int     # 1 stable, 2 beta, 3 alpha
    date: str


@dataclass
class Hit:
    """A CurseForge project as shown in search results."""
    id: int
    name: str
    author: str = ""
    downloads: int = 0
    url: str = ""
    version: str = ""


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


def download_url(f: CurseFile) -> str:
    return CDN_URL.format(a=f.id // 1000, b=f.id % 1000, name=urllib.parse.quote(f.file_name))


# ---------------------------------------------------------------- relay (official API format)
def _relay(path: str, **params):
    query = urllib.parse.urlencode(params)
    return net.get_json(RELAY + path + ("?" + query if query else ""), 20)


def _hit(mod: dict) -> Hit:
    stable = [f for f in mod.get("latestFiles") or [] if f.get("releaseType") == 1] or (mod.get("latestFiles") or [])
    newest = max(stable, key=lambda f: str(f.get("fileDate") or ""), default={})
    authors = mod.get("authors") or []
    return Hit(id=int(mod["id"]), name=str(mod.get("name", "")), author=str(authors[0].get("name", "")) if authors else "",
               downloads=int(mod.get("downloadCount") or 0),
               url=str((mod.get("links") or {}).get("websiteUrl") or PAGE_URL.format(pid=mod["id"])),
               version=re.sub(r"\.zip$", "", str(newest.get("displayName") or ""), flags=re.I))


def search(text: str, limit: int = 30) -> list[Hit]:
    """Search WoW add-ons by name, most popular first."""
    data = _relay("mods/search", gameId=1, searchFilter=text, pageSize=limit, sortField=2, sortOrder="desc")
    return [_hit(m) for m in data.get("data") or []]


def mod(pid: int) -> Hit:
    return _hit(_relay(f"mods/{pid}")["data"])


def id_from_slug(slug: str) -> int:
    """Project id of a CurseForge page slug (relay first, cfwidget as a fallback)."""
    try:
        for m in _relay("mods/search", gameId=1, slug=slug).get("data") or []:
            if m.get("slug") == slug:
                return int(m["id"])
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return int(project_info(f"wow/addons/{slug}")["id"])


def description(pid: int) -> str:
    """HTML description of a project."""
    try:
        return str(_relay(f"mods/{pid}/description").get("data") or "")
    except (urllib.error.URLError, OSError, ValueError):
        return str(project_info(pid).get("description") or "")


# ---------------------------------------------------------------- cfwidget fallback
def project_info(project) -> dict:
    """cfwidget record of a project, given its id or a path such as "wow/addons/centerstage"."""
    return net.get_json(WIDGET_URL.format(path=project), 20)


def slug_candidates(query: str) -> list[str]:
    """Page slugs a typed name may correspond to: "Hekili Forever" -> hekili-forever, hekiliforever, hekili."""
    plain = unicodedata.normalize("NFKD", query).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", plain)
    if not words:
        return []
    out = ["-".join(words), "".join(words)]
    if len(words) > 1 and len(words[0]) >= 3:
        out.append(words[0])
    return list(dict.fromkeys(out))


def _widget_hit(info: dict) -> Hit:
    files = info.get("files") or []
    stable = next((f for f in files if f.get("type") == "release"), None) or (files[0] if files else {})
    members = info.get("members") or []
    return Hit(id=int(info["id"]), name=str(info.get("title", "")),
               author=str(members[0].get("username", "")) if members else "",
               downloads=int((info.get("downloads") or {}).get("total") or 0),
               url=str((info.get("urls") or {}).get("curseforge") or PAGE_URL.format(pid=info["id"])),
               version=str(stable.get("display") or stable.get("name") or ""))


def _guess_by_slug(query: str) -> list[Hit]:
    def one(slug: str):
        try:
            return project_info(f"wow/addons/{slug}")
        except (urllib.error.URLError, OSError, ValueError):
            return None

    slugs = slug_candidates(query)
    if not slugs:
        return []
    with ThreadPoolExecutor(len(slugs)) as pool:
        found = [info for info in pool.map(one, slugs) if info and info.get("id")]
    return [_widget_hit(i) for i in {info["id"]: info for info in found}.values()]


def find_by_name(query: str) -> list[Hit]:
    """Projects matching a typed name: the relay's search, or guessed page slugs when the relay is unreachable."""
    try:
        return search(query)
    except (urllib.error.URLError, OSError, ValueError):
        return _guess_by_slug(query)


# ---------------------------------------------------------------- links and versions
def slug_of(text: str) -> str:
    """The page slug in a CurseForge add-on link, or an empty string."""
    m = SLUG_RE.search(text or "")
    return m.group(1) if m else ""


def resolve(text: str) -> int:
    """Project id from a number or from a CurseForge page link."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    slug = slug_of(text)
    if not slug:
        raise OSError("Lien CurseForge non reconnu (attendu : curseforge.com/wow/addons/nom).")
    return id_from_slug(slug)


def version_key(text: str) -> str:
    """The version number inside a label ("Auctionator 341", "v0.5.0-forever" -> "0.5.0")."""
    m = re.search(r"\d+(?:\.\d+)*", text or "")
    return m.group() if m else (text or "").strip().lower()
