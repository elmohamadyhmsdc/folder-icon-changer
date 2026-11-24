import os
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from PyQt6.QtCore import QByteArray, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QListView, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter,
    QStackedWidget, QStatusBar, QTableWidget, QTableWidgetItem, QTreeView,
    QVBoxLayout, QWidget,
)

from app.config import load_prefs, save_prefs
from app.services import icon_applier, organizer
from app.services.detector import ContentType, DetectionResult, detect
from app.services.image_pipeline import build_ico
from app.services.searcher import SearchResult, get_missing_keys_info, search_for
from app.ui.organize_dialog import OrganizeDialog
from app.ui.preview_widget import PreviewWidget
from app.ui.search_dialog import SearchDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.styles import DARK_STYLE
from app.ui.widgets import ElidedLabel
from app.utils import threads
from app.utils.admin import relaunch_as_admin

_STATUS_PENDING = "Pending"
_STATUS_SEARCHING = "Searching…"
_STATUS_READY = "Ready to apply"
_STATUS_APPLYING = "Applying…"
_STATUS_DONE = "Applied ✓"
_STATUS_FAILED = "Failed ✗"
_STATUS_SKIPPED = "Skipped"
_STATUS_NOMATCH = "No match"

# status -> (foreground, background tint, tooltip)
_STATUS_STYLE = {
    _STATUS_PENDING:   ("#7a7aa6", "#101018", "Not searched yet — press “Find Icons”."),
    _STATUS_SEARCHING: ("#60a5fa", "#0d1a2e", "Looking up artwork…"),
    _STATUS_READY:     ("#fbbf24", "#1e180a", "A match was found. Review it, then apply."),
    _STATUS_APPLYING:  ("#818cf8", "#0f0f22", "Building and applying the icon…"),
    _STATUS_DONE:      ("#4ade80", "#0a1c0f", "The icon is applied."),
    _STATUS_FAILED:    ("#f87171", "#1c0a0a", "Applying the icon failed."),
    _STATUS_SKIPPED:   ("#6a6a92", "#0e0e16", "Skipped — “Find Icons” ignores this folder."),
    _STATUS_NOMATCH:   ("#fb923c", "#1c1209", "No artwork found. Use “Search…” with a different title."),
}

_COL_NAME, _COL_TYPE, _COL_MATCH, _COL_CONF, _COL_STATUS = range(5)
_IGNORED_DIRS = {"$recycle.bin", "system volume information", "found.000"}


@dataclass
class FolderEntry:
    path: str
    name: str
    detection: Optional[DetectionResult] = None
    results: List[SearchResult] = field(default_factory=list)
    selected_result: Optional[SearchResult] = None
    applied: bool = False        # we put an icon on this folder
    skipped: bool = False        # user pressed Skip — excluded from Find Icons
    in_batch: bool = False       # part of the running batch (drives progress)
    status: str = _STATUS_PENDING
    error: str = ""

    @property
    def can_apply(self) -> bool:
        return bool(self.selected_result and self.selected_result.image_url)


class _ProcessWorker(QThread):
    """Detection + search for a single folder."""
    done = pyqtSignal(object, object, list)   # FolderEntry, DetectionResult, [SearchResult]

    def __init__(self, entry: FolderEntry):
        super().__init__()
        self.entry = entry

    def run(self):
        det = detect(self.entry.name, scan_contents=False)
        try:
            results = search_for(self.entry.name, det.content_type)
        except Exception:
            results = []
        self.done.emit(self.entry, det, results)


class _ApplyWorker(QThread):
    """Full image pipeline + icon application for a single folder."""
    done = pyqtSignal(object, bool, str)  # FolderEntry, success, error_message

    def __init__(self, entry: FolderEntry):
        super().__init__()
        self.entry = entry

    def run(self):
        result = self.entry.selected_result
        if result is None or not result.image_url:
            self.done.emit(self.entry, False, "This match has no artwork to use.")
            return
        with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as f:
            ico_path = f.name
        ok = False
        error_msg = ""
        try:
            ok = build_ico(
                result.image_url,
                ico_path,
                content_type=ContentType(self.entry.detection.content_type) if self.entry.detection else ContentType.UNKNOWN,
                score=result.score,
            )
            if ok:
                ok, error_msg = icon_applier.apply(self.entry.path, ico_path)
            else:
                error_msg = "Couldn't download or build the icon image (check your connection)."
        except Exception as exc:
            import traceback
            traceback.print_exc()
            error_msg = str(exc)
        finally:
            if os.path.exists(ico_path):
                os.remove(ico_path)
        self.done.emit(self.entry, ok, error_msg)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class MainWindow(QMainWindow):
    def __init__(self, is_admin: bool = True):
        super().__init__()
        self._is_admin = is_admin
        self._prefs = load_prefs()
        self._entries: List[FolderEntry] = []
        self._alt_building = False
        self._api_banner_dismissed = False
        self.setAcceptDrops(True)
        self._setup_ui()
        self.setStyleSheet(DARK_STYLE)
        self._setup_shortcuts()
        if not self._restore_geometry():
            self.resize(1200, 760)
        self._update_state()

    # ══ UI construction ═══════════════════════════════════════════

    def _setup_ui(self):
        self.setWindowTitle("Folder Icon Changer")
        self.setMinimumSize(980, 600)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        self._admin_banner = self._build_banner(
            "bannerWarn", "⚠",
            "Not running as Administrator — icon changes may fail on protected folders.",
            "Restart as Administrator", self._restart_as_admin,
            "#fbbf24", "#fde68a", "#7a5500", "#a07000", self._dismiss_admin_banner,
        )
        self._admin_banner.setVisible(not self._is_admin)
        root.addWidget(self._admin_banner)

        self._api_key_banner = self._build_banner(
            "bannerInfo", "🔑",
            "Add free API keys to search Movies, TV Shows and Games (anime works without one).",
            "Add API keys", self._open_settings,
            "#818cf8", "#a5b4fc", "#4a3a8a", "#6a5ab0", self._dismiss_api_banner,
        )
        self._api_key_banner.setVisible(False)
        root.addWidget(self._api_key_banner)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 8)
        content_layout.setSpacing(12)

        # Left: empty state / table
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_empty_state())
        self._table = self._build_table()
        self._stack.addWidget(self._table)

        # Right: details panel (scrollable so it never clips on short windows)
        self._side = self._build_side_panel()

        content_layout.addWidget(self._stack, 1)
        content_layout.addWidget(self._side, 0)
        root.addWidget(content, 1)

        # Status bar
        self._status_bar = QStatusBar()
        self._status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self._status_bar)
        self._summary_label = QLabel("")
        self._summary_label.setObjectName("hint")
        self._progress = QProgressBar()
        self._progress.setFixedWidth(180)
        self._progress.setFormat("%v / %m")
        self._progress.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress)
        self._status_bar.addPermanentWidget(self._summary_label)
        self._status_bar.showMessage("Ready — add some folders to begin.")

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("toolbarFrame")
        bar = QHBoxLayout(frame)
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(6)

        def btn(text, tip, slot, name=None):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if name:
                b.setObjectName(name)
            b.clicked.connect(slot)
            return b

        bar.addWidget(btn("＋  Add Folders", "Pick one or more folders  (Ctrl+O)", self._pick_folders))
        bar.addWidget(btn("Add Subfolders…", "Add every folder inside a library folder  (Ctrl+Shift+O)",
                          self._pick_parent))
        bar.addWidget(btn("🎬  Organize Movies…",
                          "Put loose movie files into their own folders named after the movie  (Ctrl+M)",
                          self._organize_movies))

        sep = QFrame()
        sep.setFixedSize(1, 24)
        sep.setStyleSheet("background-color: #2e2e45;")
        bar.addSpacing(4)
        bar.addWidget(sep)
        bar.addSpacing(4)

        self._btn_find = btn("▶  Find Icons", "Search artwork for every folder in the list  (F5)",
                             self._run_all, "primaryBtn")
        bar.addWidget(self._btn_find)
        self._btn_apply_all = btn("✓  Apply All Ready", "Apply every match that is waiting for your approval",
                                  self._apply_all_ready)
        bar.addWidget(self._btn_apply_all)

        bar.addStretch()

        self._btn_more = QPushButton("⋯")
        self._btn_more.setObjectName("iconBtn")
        self._btn_more.setToolTip("More actions")
        more = QMenu(self)
        more.addAction("Undo All Icons…", self._undo_all)
        more.addAction("Undo Last Organize…", self._undo_organize)
        more.addSeparator()
        more.addAction("Clear List", self._clear_list)
        self._btn_more.setMenu(more)
        bar.addWidget(self._btn_more)

        bar.addWidget(btn("⚙", "Settings  (Ctrl+,)", self._open_settings, "iconBtn"))
        return frame

    def _build_banner(self, object_name, icon, text, button_text, slot,
                      icon_color, text_color, btn_border, btn_hover, dismiss_slot) -> QFrame:
        banner = QFrame()
        banner.setObjectName(object_name)
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(14, 6, 8, 6)
        lay.setSpacing(10)

        ic = QLabel(icon)
        ic.setStyleSheet(f"color: {icon_color}; font-size: 15px;")
        lay.addWidget(ic)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {text_color}; font-size: 12px;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)

        b = QPushButton(button_text)
        b.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {text_color}; border: 1px solid {btn_border};"
            f" border-radius: 5px; padding: 3px 12px; min-height: 22px; }}"
            f"QPushButton:hover {{ background: {btn_hover}; color: #ffffff; }}"
        )
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        lay.addWidget(b)

        x = QPushButton("✕")
        x.setToolTip("Dismiss")
        x.setFixedWidth(30)
        x.setStyleSheet(f"QPushButton {{ color: {text_color}; background: transparent; border: none; min-height: 22px; padding: 0; }}"
                        f"QPushButton:hover {{ color: #ffffff; }}")
        x.clicked.connect(dismiss_slot)
        lay.addWidget(x)
        return banner

    def _build_empty_state(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(640)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(36, 32, 36, 28)
        lay.setSpacing(10)

        glyph = QLabel("🗂")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setStyleSheet("font-size: 44px; background: transparent;")
        lay.addWidget(glyph)

        title = QLabel("Give your folders real artwork")
        title.setObjectName("h1")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        sub = QLabel("Add your movie, TV, anime or game folders. We find the poster and turn it into a folder icon.")
        sub.setObjectName("hint")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(8)
        for i, (text, slot) in enumerate((
            ("＋  Add Folders", self._pick_folders),
            ("Add Subfolders…", self._pick_parent),
            ("🎬  Organize Movies…", self._organize_movies),
        )):
            b = QPushButton(text)
            if i == 0:
                b.setObjectName("primaryBtn")
            b.setMinimumHeight(40)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        lay.addSpacing(10)

        steps = QLabel("<b>1</b>  Add folders   →   <b>2</b>  Find icons   →   <b>3</b>  Review &amp; apply")
        steps.setTextFormat(Qt.TextFormat.RichText)
        steps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        steps.setStyleSheet("color: #8a8ab8; font-size: 12px; background: transparent;")
        lay.addWidget(steps)

        tip = QLabel("Tip: drag &amp; drop folders anywhere in this window.<br>"
                     "Movie files lying loose in a folder? “Organize Movies…” gives each one its own folder first.")
        tip.setTextFormat(Qt.TextFormat.RichText)
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setWordWrap(True)
        tip.setObjectName("hint")
        lay.addWidget(tip)

        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(card, 4)
        h.addStretch(1)
        outer.addLayout(h)
        outer.addStretch(2)
        return page

    def _build_table(self) -> QTableWidget:
        t = QTableWidget(0, 5)
        t.setHorizontalHeaderLabels(["Folder", "Type", "Best match", "Match %", "Status"])
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(_COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_MATCH, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(_COL_CONF, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_STATUS, QHeaderView.ResizeMode.Fixed)
        t.setColumnWidth(_COL_STATUS, 150)
        hh.setHighlightSections(False)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        t.setWordWrap(False)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(38)
        t.setAlternatingRowColors(True)
        t.setShowGrid(False)
        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(self._show_context_menu)
        t.itemSelectionChanged.connect(self._on_selection_changed)
        t.doubleClicked.connect(lambda _idx: self._search_again())
        return t

    def _build_side_panel(self) -> QWidget:
        """Right-hand panel: scrollable details on top, action buttons pinned below."""
        details = QWidget()
        lay = QVBoxLayout(details)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(8)

        lbl = QLabel("SELECTED FOLDER")
        lbl.setObjectName("sectionLabel")
        lay.addWidget(lbl)
        self._side_name = QLabel("")
        self._side_name.setObjectName("h2")
        self._side_name.setWordWrap(True)
        lay.addWidget(self._side_name)
        self._side_path = ElidedLabel("")
        self._side_path.setObjectName("hint")
        lay.addWidget(self._side_path)

        self._preview = PreviewWidget()
        lay.addWidget(self._preview)

        self._alt_label = QLabel("OTHER MATCHES — click one to switch")
        self._alt_label.setObjectName("sectionLabel")
        lay.addWidget(self._alt_label)
        self._alt_list = QListWidget()
        self._alt_list.setMinimumHeight(120)
        self._alt_list.setMaximumHeight(190)
        self._alt_list.currentRowChanged.connect(self._on_alt_changed)
        lay.addWidget(self._alt_list)

        self._error_box = QLabel("")
        self._error_box.setObjectName("errorBox")
        self._error_box.setWordWrap(True)
        self._error_box.setVisible(False)
        lay.addWidget(self._error_box)
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(details)

        actions = QWidget()
        act = QVBoxLayout(actions)
        act.setContentsMargins(0, 4, 6, 0)
        act.setSpacing(6)

        self._btn_apply = QPushButton("✓  Apply Icon")
        self._btn_apply.setObjectName("primaryBtn")
        self._btn_apply.setToolTip("Apply the shown icon to the selected folder(s)  (Enter)")
        self._btn_apply.setMinimumHeight(36)
        self._btn_apply.clicked.connect(self._apply_selected)
        act.addWidget(self._btn_apply)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._btn_search = QPushButton("Search…")
        self._btn_search.setToolTip("Look for a different title  (double-click a row)")
        self._btn_search.clicked.connect(self._search_again)
        row.addWidget(self._btn_search)
        self._btn_skip = QPushButton("Skip")
        self._btn_skip.setToolTip("Leave this folder alone")
        self._btn_skip.clicked.connect(self._skip_selected)
        row.addWidget(self._btn_skip)
        self._btn_open = QPushButton("Open")
        self._btn_open.setToolTip("Open the folder in Explorer")
        self._btn_open.clicked.connect(self._open_selected_in_explorer)
        row.addWidget(self._btn_open)
        act.addLayout(row)

        self._btn_undo = QPushButton("↩  Undo Icon")
        self._btn_undo.setObjectName("dangerBtn")
        self._btn_undo.setToolTip("Restore the folder's original icon")
        self._btn_undo.clicked.connect(self._undo_selected)
        act.addWidget(self._btn_undo)

        side = QWidget()
        side.setFixedWidth(312)
        outer = QVBoxLayout(side)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.addWidget(scroll, 1)
        outer.addWidget(actions, 0)
        return side

    def _setup_shortcuts(self):
        def sc(keys, slot, widget=None, widget_only=False):
            s = QShortcut(QKeySequence(keys), widget or self)
            if widget_only:
                s.setContext(Qt.ShortcutContext.WidgetShortcut)
            s.activated.connect(slot)

        sc("Ctrl+O", self._pick_folders)
        sc("Ctrl+Shift+O", self._pick_parent)
        sc("Ctrl+M", self._organize_movies)
        sc("F5", self._run_all)
        sc("Ctrl+R", self._run_all)
        sc("Ctrl+,", self._open_settings)
        sc("Delete", self._remove_selected, self._table, True)
        sc("Return", self._apply_selected, self._table, True)
        sc("Enter", self._apply_selected, self._table, True)

    # ══ Geometry / prefs helpers ══════════════════════════════════

    def _restore_geometry(self) -> bool:
        geo = self._prefs.get("window_geometry") or ""
        if geo:
            try:
                return bool(self.restoreGeometry(QByteArray.fromHex(geo.encode())))
            except Exception:
                pass
        return False

    def _remember(self, key: str, value: str):
        prefs = load_prefs()
        prefs[key] = value
        save_prefs(prefs)
        self._prefs = prefs

    def _start_dir(self) -> str:
        d = self._prefs.get("last_dir") or ""
        return d if d and os.path.isdir(d) else ""

    def closeEvent(self, event):
        try:
            self._remember("window_geometry", bytes(self.saveGeometry().toHex()).decode())
        except Exception:
            pass
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_api_key_banner()

    # ══ Drag & drop ═══════════════════════════════════════════════

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
                u.isLocalFile() and os.path.isdir(u.toLocalFile()) for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [os.path.normpath(u.toLocalFile()) for u in event.mimeData().urls()
                 if u.isLocalFile() and os.path.isdir(u.toLocalFile())]
        event.acceptProposedAction()
        added = 0
        for p in paths:
            if self._maybe_organize_library(p, strict=True):
                continue
            added += 1 if self._add_folder(p) is not None else 0
        if added:
            self._after_adding(added)

    # ══ Adding folders ════════════════════════════════════════════

    def _pick_folders(self):
        """Pick one or more folders (Qt's own dialog supports multi-select)."""
        dlg = QFileDialog(self, "Select Folder(s)", self._start_dir())
        dlg.setFileMode(QFileDialog.FileMode.Directory)
        dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        for view in dlg.findChildren(QListView) + dlg.findChildren(QTreeView):
            view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        if dlg.exec():
            folders = [os.path.normpath(f) for f in dlg.selectedFiles()]
            added = sum(self._add_folder(f) is not None for f in folders)
            if folders:
                self._remember("last_dir", os.path.dirname(folders[0]))
            self._after_adding(added)

    def _pick_parent(self):
        parent = QFileDialog.getExistingDirectory(
            self, "Select the folder that contains your folders", self._start_dir())
        if not parent:
            return
        parent = os.path.normpath(parent)
        self._remember("last_dir", parent)
        # Loose movie files in a library folder can't get icons — offer to fix that first.
        if self._maybe_organize_library(parent, strict=False):
            return
        self._after_adding(self._add_subfolders(parent))

    def _maybe_organize_library(self, folder: str, strict: bool) -> bool:
        """Offer to organize loose movies in `folder`. Returns True if it did and
        the folder's contents were added to the list."""
        dlg = self._offer_organize(folder, ask_first=True, strict=strict)
        if dlg is None:
            return False
        self._add_subfolders(folder)
        self._after_organize(dlg)
        return True

    def _add_subfolders(self, parent: str) -> int:
        added = 0
        try:
            for name in sorted(os.listdir(parent), key=str.lower):
                if name.startswith(".") or name.lower() in _IGNORED_DIRS:
                    continue
                full = os.path.join(parent, name)
                if os.path.isdir(full) and self._add_folder(full) is not None:
                    added += 1
        except OSError as exc:
            QMessageBox.warning(self, "Can't read folder", f"Couldn't list the contents of:\n{parent}\n\n{exc}")
        return added

    def _add_folder(self, path: str) -> Optional[FolderEntry]:
        path = os.path.normpath(path)
        if any(os.path.normcase(e.path) == os.path.normcase(path) for e in self._entries):
            return None
        entry = FolderEntry(path=path, name=os.path.basename(path) or path)
        row = len(self._entries)
        self._entries.append(entry)
        self._table.insertRow(row)
        for col in range(5):
            self._table.setItem(row, col, QTableWidgetItem())
        self._refresh_row(row)
        return entry

    def _after_adding(self, added: int):
        if added:
            self._status_bar.showMessage(
                f"Added {_plural(added, 'folder')}. Press “Find Icons” (F5) to look up artwork.", 8000)
            if self._table.currentRow() < 0:
                self._table.selectRow(0)
        else:
            self._status_bar.showMessage("Nothing new to add — those folders are already in the list.", 6000)
        self._update_state()

    # ══ Organizing loose movies ═══════════════════════════════════

    def _offer_organize(self, folder: str, ask_first: bool, strict: bool = False) -> Optional[OrganizeDialog]:
        """Scan `folder` for loose movies; confirm; show the preview dialog.

        strict=True is used for dropped folders, where a single movie file is far
        more likely a movie folder than a library — only offer when there are
        several *different* movies.
        """
        moves, skipped = organizer.scan_loose_movies(folder)
        if not moves:
            return None
        if strict and not (len(moves) >= 2 and len({m.title.lower() for m in moves}) >= 2):
            return None
        if ask_first:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Loose movie files found")
            box.setText(f"<b>{_plural(len(moves), 'movie file')}</b> in “{os.path.basename(folder) or folder}” "
                        "aren't inside a folder of their own.")
            box.setInformativeText("Folder icons need a folder. Put each movie into its own folder named after it?")
            yes = box.addButton("Review && Organize…", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(yes)
            box.exec()
            if box.clickedButton() is not yes:
                return None
        dlg = OrganizeDialog(folder, moves, skipped, self)
        if dlg.exec() and dlg.result_info and dlg.result_info.moved:
            return dlg
        return None

    def _organize_movies(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose the folder that contains your loose movie files", self._start_dir())
        if not folder:
            return
        folder = os.path.normpath(folder)
        self._remember("last_dir", folder)
        moves, skipped = organizer.scan_loose_movies(folder)
        if not moves:
            extra = f"\n\n{len(skipped)} video file(s) were ignored (TV episodes or samples)." if skipped else ""
            QMessageBox.information(
                self, "Nothing to organize",
                f"No loose movie files were found directly inside:\n{folder}{extra}\n\n"
                "Movies that already live in their own folder don't need this step.")
            return
        dlg = self._offer_organize(folder, ask_first=False)
        if dlg is not None:
            self._after_organize(dlg)

    def _after_organize(self, dlg: OrganizeDialog):
        res = dlg.result_info
        for f in res.folders:
            self._add_folder(f)
        new_rows = [r for r in (self._row_of_path(f) for f in res.folders) if r >= 0]
        self._update_state()
        self._status_bar.showMessage(
            f"Organized {_plural(res.moved, 'movie')} into their own folders. "
            "Undo anytime from the ⋯ menu.", 10000)
        if new_rows:
            self._table.clearSelection()
            self._table.selectRow(new_rows[0])
            if dlg.find_icons_after:
                self._run_rows(new_rows)

    def _undo_organize(self):
        info = organizer.last_batch_summary()
        if info is None:
            QMessageBox.information(self, "Nothing to undo", "No organize operation has been recorded yet.")
            return
        parent, count = info
        ans = QMessageBox.question(
            self, "Undo last organize?",
            f"Move {_plural(count, 'movie')} back out of their folders into\n{parent}\n\n"
            "Any folder icon we applied to them is removed first, and the folders we created are deleted "
            "(only if they end up empty).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return
        restored, errors = organizer.undo_last_batch(icon_applier.undo)
        # Drop list rows whose folder is gone.
        self._remove_rows([i for i, e in enumerate(self._entries) if not os.path.isdir(e.path)])
        if errors:
            QMessageBox.warning(self, "Undo finished with problems",
                                f"Restored {_plural(restored, 'movie')}. Problems:\n\n" + "\n".join(errors[:8]))
        else:
            self._status_bar.showMessage(f"Moved {_plural(restored, 'movie')} back.", 8000)

    # ══ Row helpers ═══════════════════════════════════════════════

    def _row_of(self, entry: FolderEntry) -> int:
        """Current row of an entry (identity match), or -1 if it was removed."""
        for i, e in enumerate(self._entries):
            if e is entry:
                return i
        return -1

    def _row_of_path(self, path: str) -> int:
        for i, e in enumerate(self._entries):
            if os.path.normcase(e.path) == os.path.normcase(os.path.normpath(path)):
                return i
        return -1

    def _selected_rows(self) -> List[int]:
        return sorted({idx.row() for idx in self._table.selectionModel().selectedRows()})

    def _selected_entries(self) -> List[FolderEntry]:
        return [self._entries[r] for r in self._selected_rows() if 0 <= r < len(self._entries)]

    def _current_entry(self) -> Optional[FolderEntry]:
        row = self._table.currentRow()
        sel = self._selected_rows()
        if row in sel and 0 <= row < len(self._entries):
            return self._entries[row]
        return self._entries[sel[0]] if sel else None

    def _threshold(self) -> int:
        return load_prefs().get("auto_apply_threshold", 85)

    def _refresh_row(self, row: int):
        """Single place that paints a table row from its entry."""
        if not (0 <= row < len(self._entries)):
            return
        e = self._entries[row]
        r = e.selected_result

        def cell(col, text, tip="", color=None, align=None):
            it = self._table.item(row, col)
            it.setText(text)
            it.setToolTip(tip)
            it.setForeground(QBrush(QColor(color or "#d6d6ee")))
            it.setTextAlignment(align or (Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft))

        cell(_COL_NAME, e.name, e.path)
        cell(_COL_TYPE, e.detection.content_type.value if e.detection else "—", color="#9a9ac0")
        if r:
            title = f"{r.title} ({r.year})" if r.year else r.title
            cell(_COL_MATCH, title, f"via {r.source}")
            conf = r.confidence
            color = "#4ade80" if conf >= self._threshold() else "#fbbf24" if conf >= 60 else "#fb923c"
            cell(_COL_CONF, f"{conf:.0f}%", "How closely the title matches your folder name",
                 color, Qt.AlignmentFlag.AlignCenter)
        else:
            cell(_COL_MATCH, "—" if e.status in (_STATUS_PENDING, _STATUS_SEARCHING) else "No results",
                 color="#6a6a92")
            cell(_COL_CONF, "—", color="#6a6a92", align=Qt.AlignmentFlag.AlignCenter)

        fg, bg, tip = _STATUS_STYLE.get(e.status, ("#c8c8e8", "#0d0d12", ""))
        if e.status == _STATUS_FAILED and e.error:
            tip = e.error
        cell(_COL_STATUS, e.status, tip, fg, Qt.AlignmentFlag.AlignCenter)
        self._table.item(row, _COL_STATUS).setBackground(QBrush(QColor(bg)))

    def _set_status(self, entry: FolderEntry, status: str, error: str = ""):
        entry.status = status
        entry.error = error
        self._refresh_row(self._row_of(entry))

    # ══ Find icons (detect + search) ══════════════════════════════

    def _run_all(self):
        # Folders the user explicitly skipped stay skipped.
        self._run_rows([i for i, e in enumerate(self._entries) if not e.skipped])

    def _run_selected(self):
        rows = self._selected_rows()
        for r in rows:
            self._entries[r].skipped = False   # explicitly asked to run it
        self._run_rows(rows)

    def _run_rows(self, rows: List[int]):
        pending = [r for r in rows
                   if not (self._entries[r].applied and self._entries[r].status == _STATUS_DONE)
                   and self._entries[r].status not in (_STATUS_SEARCHING, _STATUS_APPLYING)]
        if not pending:
            self._status_bar.showMessage("Nothing to search — every folder is already done or in progress.", 5000)
            return
        self._begin_batch(len(pending))
        for row in pending:
            entry = self._entries[row]
            entry.in_batch = True
            self._set_status(entry, _STATUS_SEARCHING)
            w = _ProcessWorker(entry)
            w.done.connect(self._on_process_done)
            threads.start(w)
        self._update_state()

    def _on_process_done(self, entry: FolderEntry, detection: DetectionResult, results: List[SearchResult]):
        row = self._row_of(entry)
        if row < 0:
            return  # removed from the list while this worker was running
        entry.detection = detection
        entry.results = results
        entry.selected_result = results[0] if results else None

        if results:
            self._set_status(entry, _STATUS_READY)
        else:
            self._set_status(entry, _STATUS_NOMATCH)
            missing = get_missing_keys_info(detection.content_type)
            if missing:
                labels = ", ".join(m["label"].split("  (")[0] for m in missing)
                self._status_bar.showMessage(
                    f"No results for “{entry.name}” — missing API key: {labels}. Open ⚙ Settings to add it.", 10000)

        if results and results[0].confidence >= self._threshold() and entry.can_apply:
            self._apply_entry(entry)
        else:
            self._finish_batch_item(entry)

        if entry is self._current_entry():
            self._show_entry(entry)
        self._update_state()

    # ══ Apply / undo ══════════════════════════════════════════════

    def _apply_entry(self, entry: FolderEntry):
        self._set_status(entry, _STATUS_APPLYING)
        w = _ApplyWorker(entry)
        w.done.connect(self._on_apply_done)
        threads.start(w)

    def _on_apply_done(self, entry: FolderEntry, success: bool, error_msg: str):
        row = self._row_of(entry)
        if row < 0:
            return
        if success:
            entry.applied = True
            self._set_status(entry, _STATUS_DONE)
        else:
            self._set_status(entry, _STATUS_FAILED, error_msg or "Unknown error")
            is_permission = "permission" in error_msg.lower() or "access" in error_msg.lower()
            tip = " — try restarting as Administrator (see the banner above)" if is_permission and not self._is_admin else ""
            self._status_bar.showMessage(f"Couldn't apply “{entry.name}”: {error_msg}{tip}", 10000)
        self._finish_batch_item(entry)
        if entry is self._current_entry():
            self._show_entry(entry)
        self._update_state()

    def _apply_selected(self):
        entries = [e for e in self._selected_entries() if e.can_apply and e.status != _STATUS_APPLYING]
        if not entries:
            self._status_bar.showMessage("Nothing to apply — select a folder that has a match first.", 5000)
            return
        self._begin_batch(len(entries))
        for e in entries:
            e.skipped = False
            e.in_batch = True
            self._apply_entry(e)
        self._update_state()

    def _apply_all_ready(self):
        entries = [e for e in self._entries if e.status == _STATUS_READY and e.can_apply]
        if not entries:
            return
        self._begin_batch(len(entries))
        for e in entries:
            e.in_batch = True
            self._apply_entry(e)
        self._update_state()

    def _undo_selected(self):
        entries = [e for e in self._selected_entries() if e.applied]
        if not entries:
            return
        failed = self._undo_entries(entries)
        if failed:
            QMessageBox.warning(self, "Undo failed", "Couldn't restore the icon for:\n" + "\n".join(failed[:8]))
        else:
            self._status_bar.showMessage(f"Restored {_plural(len(entries), 'folder')}.", 5000)
        self._update_state()

    def _undo_all(self):
        entries = [e for e in self._entries if e.applied]
        if not entries:
            QMessageBox.information(self, "Nothing to undo", "No icons have been applied in this list yet.")
            return
        ans = QMessageBox.question(
            self, "Undo all icons?",
            f"Restore the original icon of {_plural(len(entries), 'folder')}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return
        failed = self._undo_entries(entries)
        if failed:
            self._status_bar.showMessage(
                f"Could not revert {len(failed)} folder(s): {', '.join(failed[:3])}" + ("…" if len(failed) > 3 else ""),
                10000)
        else:
            self._status_bar.showMessage("All icons reverted.", 6000)
        self._update_state()

    def _undo_entries(self, entries: List[FolderEntry]) -> List[str]:
        failed = []
        for e in entries:
            if icon_applier.undo(e.path):
                e.applied = False
                self._set_status(e, _STATUS_READY if e.can_apply else _STATUS_PENDING)
            else:
                failed.append(e.name)
        cur = self._current_entry()
        if cur:
            self._show_entry(cur)
        return failed

    # ══ Batch progress ════════════════════════════════════════════

    def _begin_batch(self, count: int):
        if self._progress.isVisible():
            self._progress.setMaximum(self._progress.maximum() + count)
        else:
            self._progress.setMaximum(count)
            self._progress.setValue(0)
            self._progress.setVisible(True)
        self._status_bar.showMessage("Working…")

    def _finish_batch_item(self, entry: FolderEntry):
        """Advance the progress bar once per entry of the running batch."""
        if not entry.in_batch:
            return
        entry.in_batch = False
        self._progress.setValue(self._progress.value() + 1)
        if self._progress.value() >= self._progress.maximum():
            self._progress.setVisible(False)
            ready = sum(1 for e in self._entries if e.status == _STATUS_READY)
            done = sum(1 for e in self._entries if e.status == _STATUS_DONE)
            msg = "Finished."
            if ready:
                msg += (f" {_plural(ready, 'folder')} waiting for your review — "
                        "check the match, then press “Apply All Ready”.")
            elif done:
                msg += f" {_plural(done, 'icon')} applied."
            self._status_bar.showMessage(msg, 15000)

    # ══ Selection / side panel ════════════════════════════════════

    def _on_selection_changed(self):
        self._show_entry(self._current_entry())
        self._update_state()

    def _show_entry(self, entry: Optional[FolderEntry]):
        if entry is None:
            self._side_name.setText("")
            self._side_path.setText("")
            self._preview.show_result(None)
            self._fill_alternatives(None)
            self._error_box.setVisible(False)
            return
        self._side_name.setText(entry.name)
        self._side_path.setText(entry.path)
        self._side_path.setToolTip(entry.path)
        self._preview.show_result(entry.selected_result)
        self._fill_alternatives(entry)
        if entry.status == _STATUS_FAILED and entry.error:
            self._error_box.setText(f"Couldn't apply: {entry.error}")
            self._error_box.setVisible(True)
        else:
            self._error_box.setVisible(False)

    def _fill_alternatives(self, entry: Optional[FolderEntry]):
        self._alt_building = True
        self._alt_list.clear()
        show = bool(entry and entry.results)
        self._alt_label.setVisible(show)
        self._alt_list.setVisible(show)
        if entry:
            for r in entry.results:
                year = f" ({r.year})" if r.year else ""
                score = f"  ·  ★ {r.score:.1f}" if r.score is not None else ""
                item = QListWidgetItem(f"{r.title or 'Unknown'}{year}\n{r.source}  ·  {r.confidence:.0f}% match{score}")
                item.setSizeHint(QSize(0, 56))
                self._alt_list.addItem(item)
            for i, r in enumerate(entry.results):
                if r is entry.selected_result:
                    self._alt_list.setCurrentRow(i)
                    break
        self._alt_building = False

    def _on_alt_changed(self, idx: int):
        if self._alt_building:
            return
        entry = self._current_entry()
        if entry is None or not (0 <= idx < len(entry.results)):
            return
        chosen = entry.results[idx]
        if chosen is entry.selected_result:
            return
        entry.selected_result = chosen
        entry.skipped = False
        if entry.status not in (_STATUS_SEARCHING, _STATUS_APPLYING):
            self._set_status(entry, _STATUS_READY)   # an applied icon (if any) is now out of date
        self._preview.show_result(chosen)
        self._error_box.setVisible(False)
        self._update_state()

    def _skip_selected(self):
        for e in self._selected_entries():
            e.skipped = True
            self._set_status(e, _STATUS_SKIPPED)
        self._update_state()

    def _search_again(self):
        entry = self._current_entry()
        if entry is None:
            return
        det = entry.detection
        dlg = SearchDialog(
            initial_query=det.clean_title if det else entry.name,
            initial_type=det.content_type if det else ContentType.UNKNOWN,
            parent=self,
        )
        if dlg.exec() and dlg.selected:
            entry.results = list(dlg.results)
            entry.selected_result = dlg.selected
            entry.skipped = False
            self._set_status(entry, _STATUS_READY)
            self._show_entry(entry)
            self._update_state()

    def _open_selected_in_explorer(self):
        entry = self._current_entry()
        if entry and os.path.isdir(entry.path):
            os.startfile(entry.path)

    # ══ Removing rows ═════════════════════════════════════════════

    def _remove_selected(self):
        self._remove_rows(self._selected_rows())

    def _remove_rows(self, rows: List[int]):
        if not rows:
            return
        for r in sorted(set(rows), reverse=True):
            if 0 <= r < len(self._entries):
                self._entries.pop(r)
                self._table.removeRow(r)
        if not self._entries:
            self._progress.setVisible(False)
        self._show_entry(self._current_entry())
        self._update_state()

    def _clear_list(self):
        if not self._entries:
            return
        # Workers still running hold their own FolderEntry; their results are
        # ignored once the entry is no longer in the list (see _row_of).
        self._entries.clear()
        self._table.setRowCount(0)
        self._preview.show_result(None)
        self._progress.setVisible(False)
        self._status_bar.showMessage("List cleared. Icons that were applied stay on their folders.", 6000)
        self._update_state()

    # ══ Context menu ══════════════════════════════════════════════

    def _show_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        if idx.isValid() and idx.row() not in self._selected_rows():
            self._table.selectRow(idx.row())
        entries = self._selected_entries()
        if not entries:
            return
        n = len(entries)
        menu = QMenu(self)
        menu.addAction("Find icon" if n == 1 else f"Find icons for {n} folders", self._run_selected)
        menu.addAction("Apply icon" if n == 1 else f"Apply icon to {n} folders",
                       self._apply_selected).setEnabled(any(e.can_apply for e in entries))
        menu.addAction("Search for another title…", self._search_again).setEnabled(n == 1)
        menu.addSeparator()
        menu.addAction("Skip", self._skip_selected)
        menu.addAction("Undo icon", self._undo_selected).setEnabled(any(e.applied for e in entries))
        menu.addSeparator()
        menu.addAction("Open in Explorer", self._open_selected_in_explorer).setEnabled(n == 1)
        menu.addAction("Remove from list", self._remove_selected)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    # ══ Global UI state ═══════════════════════════════════════════

    def _update_state(self):
        has_entries = bool(self._entries)
        self._stack.setCurrentIndex(1 if has_entries else 0)
        self._side.setVisible(has_entries)

        ready = sum(1 for e in self._entries if e.status == _STATUS_READY and e.can_apply)
        self._btn_find.setEnabled(has_entries)
        self._btn_apply_all.setEnabled(ready > 0)
        self._btn_apply_all.setText(f"✓  Apply All Ready ({ready})" if ready else "✓  Apply All Ready")

        sel = self._selected_entries()
        applicable = [e for e in sel if e.can_apply and e.status != _STATUS_APPLYING]
        n_applied = sum(1 for e in sel if e.applied)
        self._btn_apply.setEnabled(bool(applicable))
        self._btn_apply.setText("✓  Apply Icon" if len(applicable) <= 1 else f"✓  Apply to {len(applicable)} folders")
        self._btn_search.setEnabled(len(sel) >= 1)
        self._btn_skip.setEnabled(len(sel) >= 1)
        self._btn_undo.setEnabled(n_applied > 0)
        self._btn_undo.setText("↩  Undo Icon" if n_applied <= 1 else f"↩  Undo {n_applied} icons")
        self._btn_open.setEnabled(len(sel) == 1)

        if has_entries:
            applied = sum(1 for e in self._entries if e.status == _STATUS_DONE)
            bad = sum(1 for e in self._entries if e.status in (_STATUS_FAILED, _STATUS_NOMATCH))
            parts = [_plural(len(self._entries), "folder")]
            if ready:
                parts.append(f"{ready} ready")
            if applied:
                parts.append(f"{applied} applied")
            if bad:
                parts.append(f"{bad} need attention")
            self._summary_label.setText("   ·   ".join(parts))
        else:
            self._summary_label.setText("")

    # ══ Banners / admin / settings ════════════════════════════════

    def _dismiss_admin_banner(self):
        self._admin_banner.setVisible(False)

    def _dismiss_api_banner(self):
        self._api_banner_dismissed = True
        self._api_key_banner.setVisible(False)

    def _restart_as_admin(self):
        if relaunch_as_admin():
            QApplication.quit()
        else:
            # UAC prompt declined or elevation failed - stay open.
            self._status_bar.showMessage(
                "Could not restart as Administrator (the request was cancelled or failed).", 8000)

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._prefs = load_prefs()
            self._refresh_api_key_banner()
            self._preview.refresh()
            for i in range(len(self._entries)):
                self._refresh_row(i)   # confidence colours depend on the threshold

    @staticmethod
    def _any_api_key_missing() -> bool:
        return bool(get_missing_keys_info(ContentType.UNKNOWN))

    def _refresh_api_key_banner(self):
        self._api_key_banner.setVisible(self._any_api_key_missing() and not self._api_banner_dismissed)
