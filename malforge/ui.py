"""MalForgé main window. Code and comments are in English; only what the user sees is French."""

import os
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QInputDialog,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)

from concurrent.futures import ThreadPoolExecutor

from . import APP_NAME, __version__, curse, github, updater, wow
from .catalog import Catalog, Entry, flavor_accepts, norm_version
from .curse import version_key
from .icon import app_icon, make_image
from .installer import Manifest, install, uninstall

STYLE = """
* { font-family: "Segoe UI"; font-size: 13px; color: #e9e4dc; }
QWidget#root, QMainWindow { background: #151311; }
QLabel#wordmark { font-family: "Bahnschrift SemiBold Condensed", "Bahnschrift", "Segoe UI"; font-size: 30px; font-weight: 700; }
QLabel#muted { color: #a89f94; }
QLabel#h2 { font-size: 18px; font-weight: 600; }
QFrame#banner { background: #2a2018; border: none; border-radius: 4px; }
QLineEdit, QComboBox { background: #1d1a17; border: 1px solid #3a342e; border-radius: 4px; padding: 6px 10px;
    selection-background-color: #f26a21; }
QLineEdit:focus, QComboBox:focus { border-color: #f26a21; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #1d1a17; border: 1px solid #3a342e; selection-background-color: #2f2217; }
QPushButton { background: transparent; border: 1px solid #3a342e; border-radius: 4px; padding: 6px 14px; }
QPushButton:hover { border-color: #f26a21; }
QPushButton:disabled { color: #655d54; border-color: #2c2722; }
QPushButton#primary { background: #f26a21; border-color: #f26a21; color: #17110d; font-weight: 600; }
QPushButton#primary:hover { background: #ff7f3d; border-color: #ff7f3d; }
QPushButton#primary:disabled { background: #2c2722; border-color: #2c2722; color: #7a6f63; }
QPushButton#danger { color: #ff9a8f; }
QPushButton#danger:hover { border-color: #e5484d; }
QPushButton#tab { background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0;
    padding: 7px 12px; color: #a89f94; font-weight: 600; }
QPushButton#tab:checked { color: #ffa261; border-bottom-color: #f26a21; }
QPushButton#tab:hover { color: #e9e4dc; }
QTableWidget { background: transparent; alternate-background-color: transparent; border: none;
    border-top: 1px solid #3a342e; gridline-color: transparent; outline: none; }
QTableWidget::item { padding: 4px 8px; border-bottom: 1px solid #221e1a; }
QTableWidget::item:selected { background: #2f2217; color: #ffffff; }
QHeaderView::section { background: #151311; color: #a89f94; border: none; border-bottom: 1px solid #2c2722;
    padding: 6px 8px; font-weight: 600; }
QTextBrowser { background: transparent; border: none; border-top: 1px solid #3a342e; padding: 6px 0; }
QProgressBar { background: #2c2722; border: none; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: #f26a21; border-radius: 2px; }
QCheckBox::indicator { width: 15px; height: 15px; border-radius: 3px; border: 1px solid #4a4238; background: #1d1a17; }
QCheckBox::indicator:checked { background: #f26a21; border-color: #f26a21; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #3a342e; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QSplitter::handle { background: transparent; }
QToolTip { background: #1d1a17; color: #e9e4dc; border: 1px solid #f26a21; }
"""

OK, UPDATE, UNTRACKED = "ok", "update", "untracked"
STATUS_TEXT = {OK: "À jour", UPDATE: "Mise à jour", UNTRACKED: "Non suivi"}
STATUS_COLOR = {OK: "#86c496", UPDATE: "#ffa261", UNTRACKED: "#a89f94"}


@dataclass
class Row:
    title: str
    local: str = ""
    latest: str = ""
    status: str = UNTRACKED
    entry: Entry | None = None
    folders: list = field(default_factory=list)   # folders present in AddOns
    installed: bool = False
    notes: str = ""


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)


class Task(QRunnable):
    def __init__(self, fn, with_progress: bool = False):
        super().__init__()
        self.setAutoDelete(False)
        self.fn, self.with_progress, self.signals = fn, with_progress, _Signals()

    def run(self):
        try:
            result = self.fn(self.signals.progress.emit) if self.with_progress else self.fn()
        except Exception as exc:  # noqa: BLE001 - shown as is to the user
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)
            return
        self.signals.done.emit(result)


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1120, 620)

        self.pool = QThreadPool.globalInstance()
        self._tasks: set[Task] = set()
        self.catalog = Catalog()
        self.catalog_ready = False
        self.manifest = Manifest()
        self.paths: list[str] = []
        self.flavors: list[wow.Flavor] = []
        self.flavor: wow.Flavor | None = None
        self.rows: list[Row] = []          # installed add-ons
        self.shown: list[Row] = []         # rows shown in the table
        self.mode = "installed"
        self.queue: list[Row] = []
        self.busy = False
        self.release: updater.Release | None = None
        self._details: dict[str, dict] = {}
        self.remote_cache: dict[tuple, Entry | None] = {}   # ((kind, id), game version) -> latest Entry or None
        self._remote_busy = False
        self.curse_hits: list[Entry] = []   # CurseForge matches for the submitted search
        self.curse_query = ""
        self.query = ""                   # last submitted catalog search
        self._texts = {"installed": "", "browse": ""}   # search box content, kept per tab

        self._build()
        self._fit_to_screen()
        self._search_timer = QTimer(self, singleShot=True, interval=180)
        self._search_timer.timeout.connect(self.populate)
        QTimer.singleShot(0, self.start)

    def _fit_to_screen(self):
        """Open large enough to show everything, never bigger than the screen; remember the last size."""
        avail = QGuiApplication.primaryScreen().availableGeometry()
        saved = self.manifest.get("window_size")
        w, h = (int(saved[0]), int(saved[1])) if isinstance(saved, list) and len(saved) == 2 else (1360, 860)
        w = max(self.minimumWidth(), min(w, int(avail.width() * 0.95)))
        h = max(self.minimumHeight(), min(h, int(avail.height() * 0.92)))
        self.resize(w, h)
        self.move(avail.center() - self.rect().center())

    def closeEvent(self, event):
        self.manifest.set("window_size", [self.width(), self.height()])
        super().closeEvent(event)

    def notify(self, text: str):
        """Non-blocking warning: a modal loop started from inside a signal handler can make the window hang."""
        box = QMessageBox(QMessageBox.Icon.Warning, APP_NAME, text, QMessageBox.StandardButton.Ok, self)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.open()

    # ------------------------------------------------------------------ interface
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 12)
        root.setSpacing(10)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap.fromImage(make_image(160)).scaled(
            40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        mark = QLabel("MAL<span style='color:#f26a21'>FORGÉ</span>")
        mark.setObjectName("wordmark")
        mark.setTextFormat(Qt.TextFormat.RichText)
        head.addWidget(logo)
        head.addSpacing(4)
        head.addWidget(mark)
        head.addStretch()
        self.flavor_box = QComboBox()
        self.flavor_box.setMinimumWidth(190)
        self.flavor_box.setMaximumWidth(460)
        self.flavor_box.currentIndexChanged.connect(self.on_flavor)
        self.path_btn = QPushButton("+ Ajouter un dossier WoW")
        self.path_btn.clicked.connect(self.choose_folder)
        self.remove_btn = QPushButton("Retirer")
        self.remove_btn.setToolTip("Oublier le dossier de cette installation (rien n'est supprimé sur le disque)")
        self.remove_btn.clicked.connect(self.remove_folder)
        self.remove_btn.hide()
        head.addWidget(self.flavor_box)
        head.addWidget(self.remove_btn)
        head.addWidget(self.path_btn)
        root.addLayout(head)

        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 8, 14, 8)
        self.banner_text = QLabel("")
        self.banner_btn = QPushButton("Mettre à jour")
        self.banner_btn.setObjectName("primary")
        self.banner_btn.clicked.connect(self.self_update)
        bl.addWidget(self.banner_text, 1)
        bl.addWidget(self.banner_btn)
        self.banner.hide()
        root.addWidget(self.banner)

        bar = QHBoxLayout()
        self.tab_installed = QPushButton("Installés")
        self.tab_browse = QPushButton("Parcourir")
        for b, mode in ((self.tab_installed, "installed"), (self.tab_browse, "browse")):
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, m=mode: self.set_mode(m))
            bar.addWidget(b)
        self.tab_installed.setChecked(True)
        bar.addSpacing(14)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un add-on…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self._search_timer.start() if self.mode == "installed" else None)
        self.search.returnPressed.connect(self.run_search)
        bar.addWidget(self.search, 1)
        self.search_btn = QPushButton("Rechercher")
        self.search_btn.setObjectName("primary")
        self.search_btn.clicked.connect(self.run_search)
        bar.addWidget(self.search_btn)
        self.compat = QCheckBox("Compatibles uniquement")
        self.compat.setChecked(True)
        self.compat.toggled.connect(lambda _: self.populate())
        bar.addWidget(self.compat)
        self.curse_btn = QPushButton("Lien CurseForge / GitHub…")
        self.curse_btn.setToolTip("Installer un add-on à partir du lien de sa page CurseForge ou de son dépôt GitHub")
        self.curse_btn.clicked.connect(self.add_curse_link)
        bar.addWidget(self.curse_btn)
        self.refresh_btn = QPushButton("Actualiser")
        self.refresh_btn.clicked.connect(lambda: self.reload(force=True))
        bar.addWidget(self.refresh_btn)
        self.update_all_btn = QPushButton("Tout mettre à jour")
        self.update_all_btn.setObjectName("primary")
        self.update_all_btn.clicked.connect(self.update_all)
        bar.addWidget(self.update_all_btn)
        root.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 4)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.itemSelectionChanged.connect(self.on_select)
        self.table.doubleClicked.connect(lambda _: self.primary_action())
        split.addWidget(self.table)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 0, 0, 0)
        sl.setSpacing(8)
        self.d_title = QLabel("")
        self.d_title.setObjectName("h2")
        self.d_title.setWordWrap(True)
        self.d_meta = QLabel("")
        self.d_meta.setObjectName("muted")
        self.d_meta.setWordWrap(True)
        self.d_text = QTextBrowser()
        self.d_text.setOpenExternalLinks(True)
        btns = QHBoxLayout()
        self.d_main = QPushButton("")
        self.d_main.setObjectName("primary")
        self.d_main.clicked.connect(self.primary_action)
        self.d_remove = QPushButton("Supprimer")
        self.d_remove.setObjectName("danger")
        self.d_remove.clicked.connect(self.remove_action)
        self.d_web = QPushButton("Page web")
        self.d_web.clicked.connect(self.open_web)
        btns.addWidget(self.d_main, 1)
        btns.addWidget(self.d_web)
        btns.addWidget(self.d_remove)
        sl.addWidget(self.d_title)
        sl.addWidget(self.d_meta)
        sl.addWidget(self.d_text, 1)
        sl.addLayout(btns)
        split.addWidget(side)
        self.table.setMinimumWidth(480)
        side.setMinimumWidth(320)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 3)
        root.addWidget(split, 1)

        foot = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(220)
        self.progress.hide()
        foot.addWidget(self.status, 1)
        foot.addWidget(self.progress)
        root.addLayout(foot)
        self.setStyleSheet(STYLE)
        self.show_detail(None)

    # ------------------------------------------------------------------ background tasks
    def run(self, fn, done=None, failed=None, progress=None):
        task = Task(fn, with_progress=progress is not None)
        self._tasks.add(task)

        def finish():
            self._tasks.discard(task)

        if done:
            task.signals.done.connect(done)
        task.signals.done.connect(lambda _: finish())
        task.signals.failed.connect(failed or self.fail)
        task.signals.failed.connect(lambda _: finish())
        if progress:
            task.signals.progress.connect(progress)
        self.pool.start(task)

    def fail(self, message: str):
        self.set_busy(False)
        self.queue.clear()
        self.say(f"Erreur : {message}")

    def say(self, text: str):
        self.status.setText(text)

    def set_busy(self, busy: bool, indeterminate: bool = True):
        self.busy = busy
        self.progress.setVisible(busy)
        if busy and indeterminate:
            self.progress.setRange(0, 0)
        self.refresh_buttons()

    def on_progress(self, done: int, total: int):
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        else:
            self.progress.setRange(0, 0)

    # ------------------------------------------------------------------ startup
    def start(self):
        updater.cleanup_previous()
        if updater.running_exe():  # the old exe is only released a few seconds after the relaunch
            self._cleanup_timer = QTimer(self, interval=1000)
            self._cleanup_timer.timeout.connect(lambda: self._cleanup_timer.stop() if updater.cleanup_previous() else None)
            self._cleanup_timer.start()
        self.run(updater.check, done=self.on_release, failed=lambda _: None)

        self.set_paths(self.saved_paths(), "")
        self.load_catalog()

    def on_release(self, release):
        if release is None:
            return
        self.release = release
        self.banner_text.setText(f"<b>{APP_NAME} {release.version}</b> est disponible (tu as la {__version__}).")
        self.banner.show()

    def self_update(self):
        if not self.release:
            return
        exe = updater.running_exe()
        if not exe:
            QMessageBox.information(self, APP_NAME, "Lancé depuis les sources : mets à jour avec git pull.")
            return
        self.banner_btn.setEnabled(False)
        self.say("Téléchargement de la mise à jour…")
        self.set_busy(True, indeterminate=False)

        def work(progress):
            path = updater.download(self.release, progress)
            updater.install(exe, path)
            return exe

        def done(path):
            updater.relaunch(path)
            QApplication.quit()

        def failed(msg):
            self.banner_btn.setEnabled(True)
            self.fail(msg)

        self.run(work, done=done, failed=failed, progress=self.on_progress)

    def load_catalog(self, force: bool = False):
        self.say("Chargement du catalogue WoWInterface…")
        self.set_busy(True)

        def done(_):
            self.catalog_ready = True
            self.set_busy(False)
            self.say(f"{fmt_int(len(self.catalog.entries))} add-ons au catalogue.")
            self.rescan()

        self.run(lambda: self.catalog.load(force), done=done)

    # ------------------------------------------------------------------ WoW folders / game versions
    def saved_paths(self) -> list[str]:
        paths = list(self.manifest.get("wow_paths") or [])
        old = self.manifest.get("wow_path", "")  # legacy single-folder setting
        if old and old not in paths:
            paths.append(old)
        return paths or wow.common_locations()[:1]

    def choose_folder(self):
        """Add a WoW folder to the saved list; every installation stays available in the drop-down."""
        start = (self.paths[-1] if self.paths else "") or (wow.common_locations() or [""])[0]
        path = QFileDialog.getExistingDirectory(self, "Ajouter un dossier World of Warcraft", start)
        if not path:
            return
        found = wow.detect_flavors(path)
        if not found:
            QMessageBox.warning(self, APP_NAME, "Aucune version de WoW trouvée dans ce dossier.\n"
                                "Choisis le dossier qui contient _retail_, _classic_…")
            return
        self.set_paths(self.paths + [os.path.abspath(path)], found[0].path)

    def remove_folder(self):
        if self.flavor and self.flavor.root in self.paths:
            self.set_paths([p for p in self.paths if p != self.flavor.root], "")

    def set_paths(self, paths: list[str], prefer: str):
        self.paths = [p for p in dict.fromkeys(paths) if os.path.isdir(p)]
        self.manifest.set("wow_paths", self.paths)
        seen, flavors = set(), []
        for p in self.paths:
            for f in wow.detect_flavors(p):
                if f.path.lower() not in seen:
                    seen.add(f.path.lower())
                    flavors.append(f)
        self.flavors = flavors
        multi = len({f.root for f in flavors}) > 1
        self.flavor_box.blockSignals(True)
        self.flavor_box.clear()
        for f in flavors:
            self.flavor_box.addItem(f"{f.label}  ·  {f.root}" if multi else f.label, f.path)
        prefer = prefer or self.manifest.get("flavor_path", "")
        index = next((i for i, f in enumerate(flavors) if f.path == prefer), 0)
        self.flavor_box.setCurrentIndex(index if flavors else -1)
        self.flavor_box.blockSignals(False)
        self.remove_btn.setVisible(bool(flavors))
        if not flavors:
            self.flavor = None
            self.say("Ajoute ton dossier World of Warcraft pour commencer.")
            self.rescan()
        else:
            self.on_flavor()

    def on_flavor(self):
        i = self.flavor_box.currentIndex()
        if i < 0 or i >= len(self.flavors):
            return
        self.flavor = self.flavors[i]
        self.manifest.set("flavor_path", self.flavor.path)
        self.flavor_box.setToolTip(self.flavor.path)
        self.rescan()

    def reload(self, force: bool = False):
        if force:
            self.remote_cache.clear()
            self.load_catalog(force=True)
        else:
            self.rescan()

    # ------------------------------------------------------------------ data
    def rescan(self):
        """Re-read the installed add-ons and match them against the catalogs."""
        if not self.flavor:
            self.rows = []
            self.populate()
            return
        installed = wow.scan_addons(self.flavor)
        by_folder = {i.folder.lower(): i for i in installed}
        records = self.manifest.records(self.flavor)
        claimed, rows, pending = set(), [], []
        for item in installed:
            if item.folder.lower() in claimed:
                continue
            entry = self.catalog.match(item.folder, item.wowi_id) if self.catalog_ready else None
            if entry and not flavor_accepts(self.flavor.key, entry.majors):
                entry = None
            if entry and entry.key not in records and entry.uid != item.wowi_id:
                # Matched by folder name alone: only trust it when the local version is exactly the catalog's
                # (otherwise it may be a different add-on or a fork).
                if norm_version(item.version) and norm_version(item.version) == norm_version(entry.version):
                    records[entry.key] = {"version": entry.version, "folders": list(entry.folders), "name": entry.name}
                    self.manifest.save()
                else:
                    entry = None
            if entry is None:
                # A CurseForge id or page, or a GitHub repo, named in the .toc: an explicit link, so reliable
                # (unlike a folder name).
                ref = self._remote_ref(item)
                if ref:
                    cached = self.remote_cache.get((ref, self.flavor.key), False)
                    if cached is False:
                        pending.append((ref, item))
                    else:
                        entry = cached
            if entry:
                if entry.source == "wowi":
                    present = [f for f in entry.folders if f.lower() in by_folder] or [item.folder]
                    main = by_folder.get(entry.folders[0].lower(), item) if entry.folders else item
                else:
                    # The main folder, those carrying the same id, and its modules (Name_Module).
                    root = entry.folders[0].lower() if entry.folders else item.folder.lower()
                    present = [i.folder for i in installed
                               if i.folder.lower() == root or i.folder.lower().startswith(root + "_")
                               or (entry.source == "curse" and entry.uid and i.curse_id == entry.uid)]
                    main = by_folder.get(root, item)
                claimed.update(f.lower() for f in present)
                local = (records.get(entry.key) or {}).get("version") or main.version
                same = norm_version if entry.source == "wowi" else version_key
                outdated = bool(same(local)) and same(local) != same(entry.version)
                rows.append(Row(entry.name, local, entry.version, UPDATE if outdated else OK, entry, present, True, main.notes))
            else:
                claimed.add(item.folder.lower())
                rows.append(Row(item.title, item.version, "", UNTRACKED, None, [item.folder], True, item.notes))
        rows.sort(key=lambda r: (r.status != UPDATE, r.title.lower()))
        self.rows = rows
        self.populate()
        if pending and not self._remote_busy:
            self.fetch_remote(pending)

    @staticmethod
    def _remote_ref(item):
        """Where to look an installed add-on up, from the links in its .toc: CurseForge id, CurseForge slug or GitHub."""
        if item.curse_id:
            return ("c", item.curse_id)
        if item.curse_slug:
            return ("s", item.curse_slug)
        if item.github:
            return ("g", item.github)
        return None

    def fetch_remote(self, pending: list):
        """Look up, in the background, the latest version of add-ons linked to CurseForge or GitHub."""
        self._remote_busy = True
        flavor_key = self.flavor.key
        refs: dict = {}
        for ref, item in pending:
            refs.setdefault(ref, item)   # first folder (alphabetical) is the main one: "Hekili", not "Hekili_Druid"

        def one(ref):
            kind, value = ref
            item = refs[ref]
            base = dict(name=item.title, author=item.author, downloads=0, monthly=0, folders=[item.folder], majors=[], updated=0)
            try:
                if kind == "g":
                    rel = github.latest_release(value, flavor_key)
                    if rel is None:
                        return ref, None
                    return ref, Entry(uid=0, version=rel.tag, url=f"https://github.com/{value}", source="github",
                                      repo=value, file_name=rel.asset_name, size=rel.size, **base)
                pid = value if kind == "c" else curse.id_from_slug(value)
                cf = curse.latest_file(pid, flavor_key)
                if cf is None:
                    return ref, None
                return ref, Entry(uid=pid, version=cf.name, url=curse.PAGE_URL.format(pid=pid), source="curse",
                                  file_id=cf.id, file_name=cf.file_name, size=cf.size, **base)
            except Exception:  # noqa: BLE001 - network or site down: retried on refresh
                return ref, None

        def work():
            with ThreadPoolExecutor(6) as pool:
                return list(pool.map(one, refs))

        def done(results):
            self._remote_busy = False
            for ref, entry in results:
                self.remote_cache[(ref, flavor_key)] = entry
            self.rescan()

        self.run(work, done=done)

    def populate(self):
        # Browse mode only uses the query that was submitted, never the half-typed text.
        text = self.query if self.mode == "browse" else self.search.text().strip()
        self.table.setUpdatesEnabled(False)
        self.table.clearContents()
        installed_uids = {r.entry.key: r for r in self.rows if r.entry}
        if self.mode == "installed":
            words = text.lower().split()
            self.shown = [r for r in self.rows if all(w in f"{r.title} {' '.join(r.folders)}".lower() for w in words)]
            heads = ["Add-on", "Installée", "Dernière", "État"]
        else:
            if not self.catalog_ready:
                self.shown = []
            else:
                fkey = self.flavor.key if self.flavor else ""
                found = self.catalog.search(text, fkey, self.compat.isChecked())
                if self.curse_query == text and self.curse_hits:
                    # CurseForge results (API key) merged with WoWInterface's, without duplicate names.
                    names = {e.name.lower() for e in found}
                    extra = [e for e in self.curse_hits if e.name.lower() not in names
                             and (not self.compat.isChecked() or flavor_accepts(fkey, e.majors))]
                    found = found + extra
                low = text.lower()
                # Exact name first, then names starting with the query, then the most downloaded.
                found = sorted(found, key=lambda e: (e.name.lower() != low, not e.name.lower().startswith(low), -e.downloads)) if low else found
                self.shown = [installed_uids.get(e.key) or Row(e.name, "", e.version, UNTRACKED, e) for e in found]
            heads = ["Add-on", "Auteur", "Version", "Téléchargements"]
        self.table.setHorizontalHeaderLabels(heads)
        self.table.setRowCount(len(self.shown))
        for i, r in enumerate(self.shown):
            if self.mode == "installed":
                cells = [r.title, r.local or "—", r.latest or "—", STATUS_TEXT[r.status]]
                color = STATUS_COLOR[r.status]
            else:
                e = r.entry
                cells = [r.title, e.author, e.version, fmt_int(e.downloads)]
                color = STATUS_COLOR[r.status] if r.installed else None
            for c, value in enumerate(cells):
                it = QTableWidgetItem(value)
                if c == 3 and color:
                    it.setForeground(QColor(color))
                if self.mode == "browse" and c == 3:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if self.mode == "browse" and c == 0 and r.installed:
                    it.setText("✓  " + r.title)
                self.table.setItem(i, c, it)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setUpdatesEnabled(True)
        n = sum(1 for r in self.rows if r.status == UPDATE)
        self.tab_installed.setText(f"Installés ({len(self.rows)})")
        self.update_all_btn.setText(f"Tout mettre à jour ({n})" if n else "Tout mettre à jour")
        self.compat.setVisible(self.mode == "browse")
        self.curse_btn.setVisible(self.mode == "browse")
        self.search_btn.setVisible(self.mode == "browse")
        if self.shown:
            self.table.selectRow(0)
        else:
            self.show_detail(None)
        self.refresh_buttons()

    def set_mode(self, mode: str):
        self._texts[self.mode] = self.search.text()
        self.mode = mode
        self.search.blockSignals(True)
        self.search.setText(self._texts[mode])
        self.search.blockSignals(False)
        self.tab_installed.setChecked(mode == "installed")
        self.tab_browse.setChecked(mode == "browse")
        self.search.setPlaceholderText("Nom d'un add-on, puis Entrée…" if mode == "browse" else "Filtrer mes add-ons…")
        self.populate()

    # ------------------------------------------------------------------ details
    def current(self) -> Row | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or rows[0].row() >= len(self.shown):
            return None
        return self.shown[rows[0].row()]

    def on_select(self):
        self.show_detail(self.current())

    def show_detail(self, row: Row | None):
        if row is None:
            self.d_title.setText("")
            self.d_meta.setText("")
            self.d_text.setHtml("<p style='color:#8f867b'>Sélectionne un add-on.</p>" if self.flavor
                                else "<p style='color:#8f867b'>Choisis ton dossier World of Warcraft en haut à droite.</p>")
            self.refresh_buttons()
            return
        self.d_title.setText(row.title)
        e = row.entry
        meta = []
        if e:
            meta += [f"par {e.author}", f"version {e.version}", f"{fmt_int(e.downloads)} téléchargements"]
        if row.installed:
            meta.append(f"installée : {row.local or 'version inconnue'}")
        self.d_meta.setText("  ·  ".join(meta) or "Non disponible sur WoWInterface")
        base = row.notes or ""
        if row.folders:
            base += ("\n\n" if base else "") + "Dossiers : " + ", ".join(row.folders)
        self.d_text.setPlainText(base)
        if e and e.source == "github":
            self.d_text.setPlainText(f"Dépôt GitHub : https://github.com/{e.repo}" + ("\n\n" + base if base else ""))
        elif e:
            if e.key in self._details:
                self.set_description(e.key, row)
            else:
                fetch = ((lambda uid=e.uid: {"description": curse.description(uid)}) if e.source == "curse"
                         else (lambda uid=e.uid: Catalog.details(uid)))
                self.run(fetch, done=lambda d, k=e.key: self.on_details(k, d), failed=lambda _: None)
        self.refresh_buttons()

    def on_details(self, key: str, detail: dict):
        self._details[key] = detail
        row = self.current()
        if row and row.entry and row.entry.key == key:
            self.set_description(key, row)

    def set_description(self, key: str, row: Row):
        detail = self._details[key]
        folders = ", ".join(row.folders)
        if row.entry.source == "curse":
            html = str(detail.get("description") or "")[:8000]
            self.d_text.setHtml((html or "<i>Pas de description.</i>") + (f"<hr><i>Dossiers : {folders}</i>" if folders else ""))
            return
        text = str(detail.get("UIDescription") or "")[:6000]
        if folders:
            text += "\n\n---\n*Dossiers : " + folders + "*"
        self.d_text.setMarkdown(text or "*Pas de description.*")

    def refresh_buttons(self):
        row = self.current() if hasattr(self, "table") else None
        idle = not self.busy
        self.d_remove.setVisible(bool(row and row.installed))
        self.d_remove.setEnabled(idle)
        self.d_web.setVisible(bool(row and row.entry))
        if row is None:
            self.d_main.setText("Installer")
            self.d_main.setEnabled(False)
        elif row.entry is None:
            self.d_main.setText("Non disponible")
            self.d_main.setEnabled(False)
        elif not row.installed:
            self.d_main.setText("Installer")
            self.d_main.setEnabled(idle and self.flavor is not None)
        elif row.status == UPDATE:
            self.d_main.setText(f"Mettre à jour vers {row.latest}")
            self.d_main.setEnabled(idle)
        else:
            self.d_main.setText("Réinstaller")
            self.d_main.setEnabled(idle)
        n = sum(1 for r in self.rows if r.status == UPDATE)
        self.update_all_btn.setEnabled(idle and n > 0)
        self.refresh_btn.setEnabled(idle)

    def open_web(self):
        row = self.current()
        if row and row.entry and row.entry.url:
            QDesktopServices.openUrl(QUrl(row.entry.url))

    # ------------------------------------------------------------------ actions
    def run_search(self):
        """Search the catalogs for what is typed in the box (Enter or the button); nothing runs while typing."""
        if self.mode != "browse":
            return
        self.query = self.search.text().strip()
        self.populate()
        text = self.query
        if len(text) < 2 or text == self.curse_query:
            return
        self.say("Recherche sur CurseForge…")

        def done(hits):
            if self.query != text:
                return  # a newer search replaced this one
            self.curse_hits = [self._hit_entry(h) for h in hits]
            self.curse_query = text
            self.populate()
            if self.curse_hits:
                self.say(f"CurseForge : {len(self.curse_hits)} correspondance(s) pour « {text} ».")
            else:
                self.say(f"Rien de plus sur CurseForge pour « {text} ». Essaie le nom exact de la page, ou « Lien CurseForge / GitHub… ».")

        self.run(lambda: curse.find_by_name(text), done=done, failed=lambda msg: self.say(msg))

    @staticmethod
    def _hit_entry(hit: "curse.Hit") -> Entry:
        """A search-result entry from a CurseForge project."""
        return Entry(uid=hit.id, name=hit.name, author=hit.author, version=hit.version, downloads=hit.downloads,
                     monthly=0, url=hit.url, folders=[], majors=[], updated=0, source="curse")

    def add_curse_link(self):
        """Install an add-on from the link of its CurseForge page or of its GitHub repository."""
        if not self.flavor or self.busy:
            return
        text, ok = QInputDialog.getText(self, "Installer depuis un lien",
                                        "Lien de la page CurseForge ou du dépôt GitHub (ou identifiant CurseForge) :")
        if not ok or not text.strip():
            return
        flavor_key = self.flavor.key
        repo = github.parse_repo(text)
        self.say("Recherche de l'add-on…")
        self.set_busy(True)

        def work():
            if repo:
                rel = github.latest_release(repo, flavor_key)
                if rel is None:
                    raise OSError("Ce dépôt ne publie aucun fichier .zip dans sa dernière release.")
                return Entry(uid=0, name=repo.split("/")[1], author=repo.split("/")[0], version=rel.tag, downloads=0,
                             monthly=0, url=f"https://github.com/{repo}", folders=[], majors=[], updated=0,
                             source="github", repo=repo, file_name=rel.asset_name, size=rel.size)
            pid = curse.resolve(text)
            cf = curse.latest_file(pid, flavor_key)
            if cf is None:
                raise OSError("Aucun fichier compatible avec cette version du jeu.")
            hit = curse.mod(pid)
            return Entry(uid=pid, name=hit.name or f"Projet {pid}", author=hit.author, version=cf.name,
                         downloads=0, monthly=0, url=curse.PAGE_URL.format(pid=pid), folders=[], majors=[], updated=0,
                         source="curse", file_id=cf.id, file_name=cf.file_name, size=cf.size)

        def done(entry):
            self.set_busy(False)
            ask = QMessageBox.question(self, APP_NAME, f"Installer {entry.name} ({entry.version}) ?")
            if ask == QMessageBox.StandardButton.Yes:
                self.queue = [Row(entry.name, "", entry.version, UNTRACKED, entry)]
                self.next_in_queue()
            else:
                self.say("")

        self.run(work, done=done)

    def primary_action(self):
        row = self.current()
        if row and row.entry and not self.busy and self.flavor:
            self.queue = [row]
            self.next_in_queue()

    def update_all(self):
        self.queue = [r for r in self.rows if r.status == UPDATE]
        self.total = len(self.queue)
        self.next_in_queue()

    def next_in_queue(self):
        if not self.queue:
            self.set_busy(False)
            self.say("Terminé.")
            self.rescan()
            return
        row = self.queue.pop(0)
        left = len(self.queue)
        self.say(f"Installation de {row.title}…" + (f"  ({left} restant{'s' if left > 1 else ''})" if left else ""))
        self.set_busy(True, indeterminate=False)
        flavor, manifest = self.flavor, self.manifest
        self.run(lambda progress: install(row.entry, flavor, manifest, progress),
                 done=lambda _: self.next_in_queue(), progress=self.on_progress)

    def remove_action(self):
        row = self.current()
        if not row or not row.installed or not self.flavor:
            return
        ask = QMessageBox.question(self, APP_NAME, f"Supprimer {row.title} ?\n\nDossiers : {', '.join(row.folders)}")
        if ask != QMessageBox.StandardButton.Yes:
            return
        uninstall(row.entry.key if row.entry else "", row.folders, self.flavor, self.manifest)
        self.say(f"{row.title} supprimé.")
        self.rescan()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    return app.exec()
