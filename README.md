# MalForgé

A simple World of Warcraft add-on manager: no account, no API key, no ads, a single `.exe`.
The interface is in French; the code, comments and docs are in English.

- Pick your WoW folder (as many as you like): MalForgé detects Retail, Classic, Classic Era, Forever...
- It lists your installed add-ons and flags the ones that have an update.
- Installed add-ons are tracked through the links in their `.toc` (WoWInterface id, CurseForge id or page, GitHub repo).
- Search by name on WoWInterface and CurseForge, then install and update in one click.
- Install from a CurseForge page link or a GitHub repository link.
- It updates itself.

Download `MalForge.exe` from the [latest release](../../releases/latest).

## Sources (none needs an account or key)

| Source | Used for |
|---|---|
| WoWInterface (`api.mmoui.com`) | full catalog, searched locally; install and update |
| CurseForge website file list + public CDN | update and install add-ons linked by id or page; page links |
| cfwidget (`api.cfwidget.com`) | CurseForge project info; finding a project from the typed name (page slug) |
| GitHub releases | update and install add-ons whose `.toc` or pasted link points to a repository that publishes a zip |

CurseForge's own search API is not used: it needs a key and refuses some keys.

## Develop

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Releases are built by the CI only (see `.github/workflows/release.yml`): bump `__version__` in
`malforge/__init__.py` and push to `main`.
