# MalForgé

A simple World of Warcraft add-on manager: no account, no ads, a single `.exe`.
The interface is in French; the code, comments and docs are in English.

- Pick your WoW folder (as many as you like): MalForgé detects Retail, Classic, Classic Era, Forever...
- It lists your installed add-ons and flags the ones that have an update.
- Search the WoWInterface catalog, install and update in one click.
- Add-ons that carry a CurseForge project id are tracked on CurseForge too, and any CurseForge page link can be installed.
- Optional free CurseForge API key to search CurseForge by name.
- It updates itself.

Download `MalForge.exe` from the [latest release](../../releases/latest).

## Sources

| Source | Needs an account/key? | Used for |
|---|---|---|
| WoWInterface (`api.mmoui.com`) | no | browsing and searching the catalog, installing, updating |
| CurseForge website + CDN | no | updating and installing add-ons whose `.toc` has `## X-Curse-Project-ID`, or from a page link |
| CurseForge API | free key (optional) | searching CurseForge by name |

## Develop

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Releases are built by the CI only (see `.github/workflows/release.yml`): bump `__version__` in
`malforge/__init__.py` and push to `main`.
