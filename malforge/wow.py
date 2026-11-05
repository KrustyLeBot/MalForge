"""Détection des dossiers WoW, des versions du jeu et des add-ons installés (lecture des .toc)."""

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
    key: str          # nom du dossier, ex. "_retail_"
    label: str        # nom lisible
    path: str         # dossier de la version (contient Interface)

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
    notes: str = ""
    deps: list = field(default_factory=list)


def _label(key: str) -> str:
    if key in FLAVOR_LABELS:
        return FLAVOR_LABELS[key]
    return key.strip("_").replace("_", " ").title() or key


def _looks_like_flavor(path: str) -> bool:
    return os.path.isdir(os.path.join(path, "Interface")) or os.path.isdir(os.path.join(path, "WTF"))


def detect_flavors(selected: str) -> list[Flavor]:
    """Les versions de WoW trouvées à partir d'un dossier choisi par l'utilisateur.

    Accepte la racine ("World of Warcraft"), un dossier de version ("_retail_"), ou même
    Interface / AddOns directement.
    """
    path = os.path.abspath(selected)
    if not os.path.isdir(path):
        return []
    # Remonte depuis AddOns / Interface vers le dossier de version.
    for _ in range(2):
        if os.path.basename(path).lower() in ("addons", "interface"):
            path = os.path.dirname(path)
    base = os.path.basename(path)
    if re.fullmatch(r"_[^_].*_", base):
        return [Flavor(base, _label(base), path)]
    found = []
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return []
    for name in names:
        full = os.path.join(path, name)
        if re.fullmatch(r"_[^_].*_", name) and os.path.isdir(full):
            found.append(Flavor(name, _label(name), full))
    # Ordre : retail d'abord, le reste alphabétique.
    found.sort(key=lambda f: (f.key != "_retail_", f.label))
    return found


def common_locations() -> list[str]:
    """Emplacements habituels, pour proposer un dossier sans que l'utilisateur ait à chercher."""
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


def scan_addons(flavor: Flavor) -> list[Installed]:
    """Les add-ons présents dans Interface/AddOns (un dossier = une entrée)."""
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
            # Certains add-ons ont un suffixe de version (Nom_Mainline.toc, Nom-Classic.toc).
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
            notes=_clean(meta.get("notes", "")),
            deps=deps,
        ))
    return result
