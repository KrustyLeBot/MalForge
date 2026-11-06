# MalForgé

World of Warcraft add-on manager (a CurseForge alternative), Python + PySide6, no account needed.
App name: **MalForgé** (with the accent). Repo, package and exe: **MalForge** (no accent). Work on `main` only.

## Language rule
Code, comments, docstrings, commit messages, README and this file are in **English**.
Only what the user sees in the interface (labels, messages, dialogs, tooltips) is **French**.

## How it works
- `malforge/wow.py`: detects game versions (`_retail_`, `_classic_`, `_classic_era_`, `_forever_`, ...) from the
  folder the user picked, and reads installed add-ons in `Interface/AddOns` (`.toc` files). Several folders can be saved.
- `malforge/catalog.py`: public WoWInterface catalog (`api.mmoui.com`, no key), cached 6 h in `%APPDATA%\MalForge`.
  Searched locally; it runs only on Enter or on the search button, never while typing.
- `malforge/curse.py`: CurseForge without a key: search, slug lookup and descriptions through the api.curse.tools relay,
  website file list, public CDN, cfwidget as a fallback (slug guesses like `hekili-forever`). CurseForge's own search API is not used
  (needs a key; some keys get 403 on it).
- `malforge/github.py`: latest GitHub release of a repo and the zip that fits the game version (BigWigs `release.json`).
- `malforge/installer.py`: download, MD5/size check, safe extraction, replacement with rollback, tracking of installs
  in `%APPDATA%\MalForge\config.json`.
- `malforge/updater.py`: self-update from the latest GitHub release (SHA-256 checked, in-place replacement).
- `malforge/ui.py`: the window. `malforge/icon.py`: the logo, drawn in code.

## Matching rules
An update is offered only for an add-on installed by MalForgé, linked by `## X-WoWI-ID`, `## X-Curse-Project-ID`,
a curseforge.com/wow/addons/<slug> link, or a GitHub repo link in `## X-Website` / `## X-Github`, or whose local
version equals the catalog's. A folder name alone is not enough
(forks and look-alike add-ons).

## Release (CI only, never locally)
To publish: raise `__version__` in `malforge/__init__.py`, push to `main`. `.github/workflows/release.yml` builds
`MalForge.exe` (PyInstaller, onefile) and creates the release `vX.Y.Z` with `MalForge.exe` and `MalForge.exe.sha256`.
If the release already exists nothing is rebuilt. A local build is only for testing:
`python -m PyInstaller --onefile --windowed --name MalForge --icon build/icon.ico main.py` (run `tools/make_icon.py` first).

## Run locally
```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```
