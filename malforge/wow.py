"""Detect WoW folders, game versions and installed add-ons (by reading the .toc files)."""

import os
import re
from dataclasses import dataclass, field

FLAVOR_LABELS = {
    "_retail_": "Retail",
    "_classic_": "Classic",
    "_classic_era_": "Classic Era",
    "_classic_ptr_": "Classic PTR",
    "_ptr_": "PTR",
    "_xptr_": "PTR 2",
    "_beta_": "Bêta",
    "_forever_": "Forever",
}


@dataclass
class Flavor:
    key: str          # folder name, e.g. "_retail_"
    label: str        # readable name
    path: str         # game version folder (contains Interface)
    root: str = ""    # folder the user picked, which this version came from

    @property
    def addons_dir(self) -> str:
        return os.path.join(self.path, "Interface", "AddOns")


@dataclass
class Installed:
    folder: str
    title: str
    version: str
    wowi_id: int = 0
    curse_id: int = 0
    curse_slug: str = ""   # from a curseforge.com/wow/addons/<slug> link in the .toc
    github: str = ""       # "owner/repo" from X-Github or X-Website
    author: str = ""
    notes: str = ""
    deps: list = field(default_factory=list)


def _label(key: str) -> str:
    if key in FLAVOR_LABELS:
        return FLAVOR_LABELS[key]
    return key.strip("_").replace("_", " ").title() or key


def _looks_like_flavor(path: str) -> bool:
    return os.path.isdir(os.path.join(path, "Interface")) or os.path.isdir(os.path.join(path, "WTF"))


def detect_flavors(selected: str) -> list[Flavor]:
    """The WoW versions found from a folder the user picked.

    Accepts the root ("World of Warcraft"), a version folder ("_retail_"), or even Interface / AddOns itself.
    """
    path = os.path.abspath(selected)
    root = path
    if not os.path.isdir(path):
        return []
    # Walk up from AddOns / Interface to the version folder.
    for _ in range(2):
        if os.path.basename(path).lower() in ("addons", "interface"):
            path = os.path.dirname(path)
    base = os.path.basename(path)
    if re.fullmatch(r"_[^_].*_", base):
        return [Flavor(base, _label(base), path, root)]
    found = []
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return []
    for name in names:
        full = os.path.join(path, name)
        if re.fullmatch(r"_[^_].*_", name) and os.path.isdir(full):
            found.append(Flavor(name, _label(name), full, root))
    # Order: retail first, the rest alphabetical.
    found.sort(key=lambda f: (f.key != "_retail_", f.label))
    return found


def common_locations() -> list[str]:
    """Usual install locations, so a folder can be suggested without the user browsing for it."""
    out = []
    for drive in "CDEFGH":
        for rel in ("World of Warcraft", r"Program Files (x86)\World of Warcraft", r"Program Files\World of Warcraft",
                    r"Games\World of Warcraft", r"Blizzard\World of Warcraft", r"WowForever\World of Warcraft"):
            p = f"{drive}:\\{rel}"
            if os.path.isdir(p):
                out.append(p)
    return out


def _parse_toc(path: str) -> dict:
    meta: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            for line in fh:
                if not line.startswith("##"):
                    if line.strip():
                        break
                    continue
                key, _, value = line[2:].partition(":")
                meta[key.strip().lower()] = value.strip()
    except OSError:
        pass
    return meta


_COLOR = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|T.*?\|t")


def _clean(text: str) -> str:
    return _COLOR.sub("", text).strip()


def _int(text: str) -> int:
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else 0


def _slug(text: str) -> str:
    m = re.search(r"curseforge\.com/wow/addons/([\w\-]+)", text or "")
    return m.group(1) if m else ""


def _repo(text: str) -> str:
    m = re.search(r"github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?(?:[/#?]|$)", text or "")
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def scan_addons(flavor: Flavor) -> list[Installed]:
    """The add-ons present in Interface/AddOns (one folder = one entry)."""
    root = flavor.addons_dir
    if not os.path.isdir(root):
        return []
    result = []
    for name in sorted(os.listdir(root), key=str.lower):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder) or name.startswith("."):
            continue
        toc = os.path.join(folder, name + ".toc")
        if not os.path.exists(toc):
            # Some add-ons use a flavor suffix (Name_Mainline.toc, Name-Classic.toc).
            tocs = [f for f in os.listdir(folder) if f.lower().endswith(".toc")]
            if not tocs:
                continue
            toc = os.path.join(folder, tocs[0])
        meta = _parse_toc(toc)
        title = _clean(meta.get("title", "")) or name
        deps = [d.strip() for d in (meta.get("dependencies") or meta.get("requireddeps") or "").split(",") if d.strip()]
        result.append(Installed(
            folder=name,
            title=title,
            version=_clean(meta.get("version", "")),
            wowi_id=_int(meta.get("x-wowi-id", "")),
            curse_id=_int(meta.get("x-curse-project-id", "")),
            curse_slug=_slug(meta.get("x-website", "")),
            github=_repo(meta.get("x-github", "")) or _repo(meta.get("x-website", "")),
            author=_clean(meta.get("author", "")),
            notes=_clean(meta.get("notes", "")),
            deps=deps,
        ))
    return result
