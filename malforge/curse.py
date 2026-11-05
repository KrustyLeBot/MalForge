"""CurseForge without an account or API key.

- file list of a project: the website's public API, by project id;
- download: CurseForge's public CDN;
- project info (title, description, downloads) and lookup by page slug: cfwidget, a free community service.

CurseForge's own search endpoint needs a key and some keys are refused, so a project is found by
its id (`## X-Curse-Project-ID` in the .toc), by the slug of its page (taken from `## X-Website`, from a
pasted link, or guessed from the name that was typed in the search box).
"""

import re
import unicodedata
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import net
from .catalog import flavor_accepts

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


def project_info(project) -> dict:
    """cfwidget record of a project, given its id or a path such as "wow/addons/centerstage"."""
    return net.get_json(WIDGET_URL.format(path=project), 20)


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
    return int(project_info(f"wow/addons/{slug}")["id"])


def version_key(text: str) -> str:
    """The version number inside a label ("Auctionator 341", "v0.5.0-forever" -> "0.5.0")."""
    m = re.search(r"\d+(?:\.\d+)*", text or "")
    return m.group() if m else (text or "").strip().lower()


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


def find_by_name(query: str) -> list[dict]:
    """cfwidget records of the projects whose page slug matches the typed name (misses are skipped silently)."""
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
    return list({info["id"]: info for info in found}.values())
