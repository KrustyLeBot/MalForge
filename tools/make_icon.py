"""Écrit build/icon.ico (icône de l'exe) à partir du dessin de malforge/icon.py. Lancé par la CI."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from malforge.icon import make_image  # noqa: E402

app = QGuiApplication([])
out = root / "build"
out.mkdir(exist_ok=True)
if not make_image(256).save(str(out / "icon.ico")):
    raise SystemExit("Impossible d'écrire icon.ico")
print("build/icon.ico")
