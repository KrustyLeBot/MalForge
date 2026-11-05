# MalForgé

Gestionnaire d'add-ons World of Warcraft (alternative à CurseForge), Python + PySide6, sans compte.
Nom de l'app : **MalForgé** (avec accent). Repo, paquet et exe : **MalForge** (sans accent). On travaille uniquement sur `main`.

## Fonctionnement
- `malforge/wow.py` : détecte les versions du jeu (`_retail_`, `_classic_`, `_classic_era_`, `_forever_`, ...) depuis le
  dossier choisi, et lit les add-ons installés dans `Interface/AddOns` (fichiers `.toc`).
- `malforge/catalog.py` : catalogue public WoWInterface (`api.mmoui.com`, sans clé), mis en cache 6 h dans `%APPDATA%\MalForge`.
- `malforge/installer.py` : téléchargement, vérif MD5, extraction sécurisée, remplacement avec retour arrière,
  suivi des installations dans `%APPDATA%\MalForge\config.json`.
- `malforge/updater.py` : auto-update de l'exe depuis la dernière release GitHub (SHA-256 vérifié, remplacement en place).
- `malforge/ui.py` : la fenêtre. `malforge/icon.py` : l'icône dessinée en code.

## Règles de rapprochement
Une mise à jour n'est proposée que pour un add-on installé par MalForgé, ou lié par `## X-WoWI-ID` dans le .toc,
ou dont la version locale est identique à celle du catalogue. Un simple nom de dossier identique ne suffit pas
(forks et add-ons homonymes). Pas de CurseForge : son API exige une clé.

## Release (CI uniquement, jamais en local)
Pour publier : augmenter `__version__` dans `malforge/__init__.py`, push sur `main`.
`.github/workflows/release.yml` construit `MalForge.exe` (PyInstaller, onefile) et crée la release `vX.Y.Z`
avec `MalForge.exe` et `MalForge.exe.sha256`. Si la release existe déjà, rien n'est refait.

## Lancer en local
```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```
