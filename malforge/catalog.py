"""Public WoWInterface catalog (mmoui API, no key or account) and matching against installed add-ons."""

import os
import re
import time
from dataclasses import dataclass

from . import net

LIST_URL = "https://api.mmoui.com/v3/game/WOW/filelist.json"
DETAIL_URL = "https://api.mmoui.com/v3/game/WOW/filedetails/{uid}.json"
CACHE_TTL = 6 * 3600


@dataclass
class Entry:
    uid: int
    name: str
    author: str
    version: str
    downloads: int
    monthly: int
    url: str
    folders: list
    majors: list      # supported game major versions (11, 4, 1...)
    updated: int      # ms since epoch
    source: str = "wowi"   # "wowi" (WoWInterface) or "curse" (CurseForge)
    file_id: int = 0       # CurseForge: file to install
    file_name: str = ""
    size: int = 0

    @property
    def key(self) -> str:
        """Tracking key in the config: the bare number for WoWInterface, prefixed for CurseForge."""
        return f"c{self.uid}" if self.source == "curse" else str(self.uid)


def _entry(raw: dict) -> Entry:
    majors = []
    for c in raw.get("UICompatibility") or []:
        m = re.match(r"\d+", str(c.get("version", "")))
        if m:
            majors.append(int(m.group()))
    return Entry(
        uid=int(raw["UID"]),
        name=str(raw.get("UIName", "")),
        author=str(raw.get("UIAuthorName", "")),
        version=str(raw.get("UIVersion", "")),
        downloads=int(raw.get("UIDownloadTotal") or 0),
        monthly=int(raw.get("UIDownloadMonthly") or 0),
        url=str(raw.get("UIFileInfoURL", "")),
        folders=list(raw.get("UIDir") or []),
        majors=majors,
        updated=int(raw.get("UIDate") or 0),
    )


# Game version -> client major number (Classic Era = 1, Classic progression = 2 to 5, Retail = 8+).
def flavor_accepts(key: str, majors: list) -> bool:
    if not majors:
        return True
    k = key.lower()
    if k in ("_retail_", "_ptr_", "_xptr_", "_beta_"):
        return any(m >= 8 for m in majors)
    if k == "_classic_era_":
        return 1 in majors
    if k in ("_classic_", "_classic_ptr_"):
        return any(2 <= m <= 7 for m in majors)
    return True  # Unknown flavor: no filtering.


def norm_version(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower().lstrip("v"))


class Catalog:
    def __init__(self):
        self.entries: list[Entry] = []
        self.by_uid: dict[int, Entry] = {}
        self.by_folder: dict[str, list[Entry]] = {}

    def load(self, force: bool = False) -> None:
        cache = os.path.join(net.app_data_dir(), "filelist.json")
        fresh = os.path.exists(cache) and time.time() - os.path.getmtime(cache) < CACHE_TTL
        raw = None
        if fresh and not force:
            raw = net.load_json(cache, None)
        if raw is None:
            try:
                raw = net.get_json(LIST_URL, 60)
                net.save_json(cache, raw)
            except OSError:
                raw = net.load_json(cache, None)  # offline: fall back to the last known catalog
                if raw is None:
                    raise
        self.entries = [_entry(r) for r in raw if "UID" in r]
        self.by_uid = {e.uid: e for e in self.entries}
        self.by_folder = {}
        for e in sorted(self.entries, key=lambda x: -x.downloads):
            for f in e.folders:
                self.by_folder.setdefault(f.lower(), []).append(e)

    def match(self, folder: str, wowi_id: int = 0) -> Entry | None:
        if wowi_id and wowi_id in self.by_uid:
            return self.by_uid[wowi_id]
        candidates = self.by_folder.get(folder.lower(), [])
        # Prefer the add-on whose main folder (first in its list) this is.
        for e in candidates:
            if e.folders and e.folders[0].lower() == folder.lower():
                return e
        return candidates[0] if candidates else None

    def search(self, text: str, flavor_key: str, only_compatible: bool = True, limit: int = 400) -> list[Entry]:
        words = [w for w in text.lower().split() if w]
        pool = self.entries
        if only_compatible:
            pool = [e for e in pool if flavor_accepts(flavor_key, e.majors)]
        if words:
            def hit(e: Entry) -> bool:
                hay = f"{e.name} {e.author} {' '.join(e.folders)}".lower()
                return all(w in hay for w in words)
            pool = [e for e in pool if hit(e)]
            # Names starting with the query come first, then popularity.
            first = words[0]
            pool.sort(key=lambda e: (not e.name.lower().startswith(first), -e.downloads))
        else:
            pool = sorted(pool, key=lambda e: -e.monthly)
        return pool[:limit]

    @staticmethod
    def details(uid: int) -> dict:
        data = net.get_json(DETAIL_URL.format(uid=uid), 30)
        return data[0] if isinstance(data, list) else data
