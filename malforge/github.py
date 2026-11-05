"""GitHub releases as an add-on source: no account needed (60 API requests per hour and IP, results are cached)."""

import re
from dataclasses import dataclass

from . import net

API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
REPO_RE = re.compile(r"github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?(?:[/#?]|$)")

# BigWigs-packager flavor names in release.json for each WoW version folder.
FLAVORS = {
    "_retail_": {"mainline"},
    "_ptr_": {"mainline"},
    "_classic_era_": {"classic"},
    "_classic_": {"mists", "cata", "wrath", "bcc", "classic"},
}


@dataclass
class GhRelease:
    repo: str
    tag: str
    asset_name: str
    url: str
    size: int


def parse_repo(text: str) -> str:
    """"owner/repo" from a GitHub link, or an empty string."""
    m = REPO_RE.search(text or "")
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def latest_release(repo: str, flavor_key: str) -> GhRelease | None:
    """The latest release of a repository and the zip that fits this game version, if it publishes one."""
    data = net.get_json(API_LATEST.format(repo=repo), 20)
    assets = {a["name"]: a for a in data.get("assets") or []}
    zips = [a for n, a in assets.items() if n.lower().endswith(".zip")]
    chosen = None
    if "release.json" in assets:
        wanted = FLAVORS.get(flavor_key.lower())
        try:
            info = net.get_json(assets["release.json"]["browser_download_url"], 20)
            for rel in info.get("releases", []):
                flavors = {m.get("flavor") for m in rel.get("metadata", [])}
                if rel.get("nolib") or rel.get("filename") not in assets:
                    continue
                if wanted is None or flavors & wanted:
                    chosen = assets[rel["filename"]]
                    break
        except (OSError, ValueError):
            pass
    if chosen is None:
        plain = [a for a in zips if "nolib" not in a["name"].lower()]
        chosen = (plain or zips or [None])[0]
    if chosen is None:
        return None
    return GhRelease(repo, str(data.get("tag_name", "")), chosen["name"], chosen["browser_download_url"],
                     int(chosen.get("size") or 0))
