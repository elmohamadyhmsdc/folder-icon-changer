import ctypes
import os
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QModelIndex
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QStatusBar, QLabel, QProgressBar, QSplitter,
    QAbstractItemView, QMessageBox, QFrame,
)

from app.config import load_prefs
from app.services.detector import detect, ContentType, DetectionResult
from app.services.searcher import SearchResult, search_for, get_missing_keys_info
from app.services.image_pipeline import build_ico
from app.services import icon_applier
from app.ui.preview_widget import PreviewWidget
from app.ui.search_dialog import SearchDialog
from app.ui.settings_dialog import SettingsDialog


@dataclass
class FolderEntry:
    path: str
    name: str
    detection: Optional[DetectionResult] = None
    results: List[SearchResult] = field(default_factory=list)
    selected_result: Optional[SearchResult] = None
    applied: bool = False


class _ProcessWorker(QThread):
    """Worker that runs detection + search for a single folder."""
    done = pyqtSignal(int, object, list)   # row_idx, DetectionResult, [SearchResult]

    def __init__(self, row: int, entry: FolderEntry):
        super().__init__()
        self.row = row
        self.entry = entry

    def run(self):
        det = detect(self.entry.name, scan_contents=False)
        results = search_for(self.entry.name, det.content_type)
        self.done.emit(self.row, det, results)


class _ApplyWorker(QThread):
    """Worker that runs the full image pipeline + icon application."""
    done = pyqtSignal(int, bool, str)  # row_idx, success, error_message

    def __init__(self, row: int, entry: FolderEntry):
        super().__init__()
        self.row = row
        self.entry = entry

    def run(self):
        result = self.entry.selected_result
        if result is None or not result.image_url:
            self.done.emit(self.row, False, "No image URL available.")
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
                error_msg = "Image pipeline failed to build .ico file."
        except Exception as exc:
            import traceback
            traceback.print_exc()
            error_msg = str(exc)
        finally:
            if os.path.exists(ico_path):
                os.remove(ico_path)
        self.done.emit(self.row, ok, error_msg)


_COL_NAME = 0
_COL_TYPE = 1
_COL_MATCH = 2
_COL_CONF = 3
_COL_STATUS = 4

_STATUS_PENDING = "Pending"
_STATUS_SEARCHING = "Searching…"
_STATUS_READY = "Ready"
_STATUS_APPLYING = "Applying…"
_STATUS_DONE = "Applied ✓"
_STATUS_FAILED = "Failed ✗"
_STATUS_SKIPPED = "Skipped"

_DARK_STYLE = """
QMainWindow, QDialog, QWidget {
    background: #0d0d12;
    color: #e2e2f0;
    font-family: "Segoe UI";
    font-size: 13px;
}

/* ── Toolbar ──────────────────────────────────────────────── */
QFrame#toolbarFrame {
    background: #13131a;
    border-bottom: 1px solid #1e1e2e;
}

/* ── Buttons — default ───────────────────────────────────── */
QPushButton {
    background: #1c1c28;
    color: #c8c8e8;
    border: 1px solid #2e2e45;
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 28px;
}
QPushButton:hover {
    background: #26263a;
    border-color: #3e3e5a;
    color: #e2e2f0;
}
QPushButton:pressed {
    background: #1a1a26;
    border-color: #6366f1;
}
QPushButton:disabled {
    color: #3a3a5a;
    border-color: #1e1e2e;
    background: #141420;
}

/* ── Buttons — primary (accent indigo) ───────────────────── */
QPushButton#primaryBtn {
    background: #4f52cc;
    color: #ffffff;
    border: 1px solid #6366f1;
    font-weight: bold;
}
QPushButton#primaryBtn:hover {
    background: #6366f1;
    border-color: #818cf8;
}
QPushButton#primaryBtn:pressed {
    background: #3b3eaa;
}
QPushButton#primaryBtn:disabled {
    background: #2a2a40;
    border-color: #2a2a40;
    color: #5a5a80;
}

/* ── Buttons — danger (red) ──────────────────────────────── */
QPushButton#dangerBtn {
    background: #3a1010;
    color: #f87171;
    border: 1px solid #7f1d1d;
}
QPushButton#dangerBtn:hover {
    background: #5c1a1a;
    border-color: #ef4444;
    color: #fca5a5;
}
QPushButton#dangerBtn:pressed {
    background: #2a0c0c;
}

/* Gear button needs tighter horizontal padding */
QPushButton#settingsToolbarButton {
    padding: 5px 6px;
    min-height: 28px;
}

/* ── Table ────────────────────────────────────────────────── */
QTableWidget {
    background: #0d0d12;
    alternate-background-color: #101018;
    gridline-color: transparent;
    color: #d0d0e8;
    border: none;
}
QTableWidget::item {
    padding: 4px 8px;
    border: none;
}
QTableWidget::item:selected {
    background: #1e1e3a;
    color: #e2e2f0;
}
QTableWidget::item:hover {
    background: #141428;
}
QHeaderView::section {
    background: #13131a;
    color: #6060a0;
    border: none;
    border-bottom: 1px solid #1e1e2e;
    border-right: 1px solid #1a1a28;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: bold;
}
QHeaderView {
    background: #13131a;
}

/* ── Splitter ─────────────────────────────────────────────── */
QSplitter::handle {
    background: #262638;
}
QSplitter::handle:horizontal {
    width: 1px;
}

/* ── Input fields ─────────────────────────────────────────── */
QLineEdit, QSpinBox {
    background: #1c1c28;
    color: #e2e2f0;
    border: 1px solid #2e2e45;
    border-radius: 5px;
    padding: 5px 8px;
    min-height: 26px;
    selection-background-color: #4f52cc;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #6366f1;
    background: #1e1e2e;
}
QLineEdit:disabled, QSpinBox:disabled {
    color: #4a4a6a;
    background: #141420;
}
QSpinBox::up-button, QSpinBox::down-button {
    background: #26263a;
    border: none;
    width: 18px;
    border-radius: 2px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background: #3a3a58;
}

/* ── ComboBox ─────────────────────────────────────────────── */
QComboBox {
    background: #1c1c28;
    color: #e2e2f0;
    border: 1px solid #2e2e45;
    border-radius: 5px;
    padding: 5px 8px;
    min-height: 26px;
}
QComboBox:focus {
    border-color: #6366f1;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: #1c1c28;
    color: #e2e2f0;
    border: 1px solid #2e2e45;
    selection-background-color: #2e2e4a;
    outline: none;
    padding: 2px;
}

/* ── CheckBox ─────────────────────────────────────────────── */
QCheckBox {
    spacing: 8px;
    color: #c8c8e8;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #3e3e5a;
    background: #1c1c28;
}
QCheckBox::indicator:checked {
    background: #6366f1;
    border-color: #6366f1;
}
QCheckBox::indicator:hover {
    border-color: #6366f1;
}

/* ── Tab widget ───────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #1e1e2e;
    background: #0d0d12;
    top: -1px;
}
QTabBar::tab {
    background: #13131a;
    color: #7070a0;
    border: 1px solid #1e1e2e;
    border-bottom: none;
    padding: 7px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #0d0d12;
    color: #e2e2f0;
    border-bottom: 1px solid #0d0d12;
}
QTabBar::tab:hover:!selected {
    background: #1a1a28;
    color: #a0a0c8;
}

/* ── List widget ──────────────────────────────────────────── */
QListWidget {
    background: #0d0d12;
    color: #d0d0e8;
    border: 1px solid #1e1e2e;
    border-radius: 6px;
    outline: none;
}
QListWidget::item {
    padding: 8px 10px;
    border-bottom: 1px solid #141420;
    min-height: 34px;
}
QListWidget::item:selected {
    background: #1e1e3a;
    color: #e2e2f0;
}
QListWidget::item:hover {
    background: #16162a;
}

/* ── Scrollbars ───────────────────────────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #2e2e45;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #5a5a90;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #2e2e45;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #5a5a90;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ── Status bar ───────────────────────────────────────────── */
QStatusBar {
    background: #0a0a10;
    color: #5a5a80;
    border-top: 1px solid #1a1a28;
    font-size: 12px;
}

/* ── Progress bar ─────────────────────────────────────────── */
QProgressBar {
    background: #1c1c28;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #9090b0;
    font-size: 11px;
    max-height: 8px;
}
QProgressBar::chunk {
    background: #6366f1;
    border-radius: 4px;
}

/* ── Dialog buttons ───────────────────────────────────────── */
QDialogButtonBox QPushButton {
    min-width: 80px;
}

/* ── Group box ────────────────────────────────────────────── */
QGroupBox {
    color: #7070a0;
    border: 1px solid #1e1e2e;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    font-size: 11px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
}

/* ── Labels & dialogs ─────────────────────────────────────── */
QLabel {
    color: #c8c8e8;
}
QMessageBox {
    background: #13131a;
}
QMessageBox QLabel {
    color: #e2e2f0;
}
"""


class MainWindow(QMainWindow):
    def __init__(self, is_admin: bool = True):
        super().__init__()
        self._is_admin = is_admin
        self._prefs = load_prefs()
        self._entries: List[FolderEntry] = []
        self._workers: List[QThread] = []
        self._pending_count = 0
        self._setup_ui()
        self.setStyleSheet(_DARK_STYLE)

    def _setup_ui(self):
        self.setWindowTitle("Folder Icon Changer")
        self.setMinimumSize(1200, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar (full-width framed container) ──────────────
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("toolbarFrame")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(10, 7, 10, 7)
        toolbar.setSpacing(5)

        btn_folder = QPushButton("+ Add Folder(s)")
        btn_folder.clicked.connect(self._pick_folders)
        toolbar.addWidget(btn_folder)

        btn_parent = QPushButton("+ Add All Subfolders…")
        btn_parent.clicked.connect(self._pick_parent)
        toolbar.addWidget(btn_parent)

        # Visual separator between Add group and Process group
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setFixedHeight(22)
        sep.setStyleSheet("background-color: #2e2e45;")
        toolbar.addWidget(sep)
        toolbar.addSpacing(2)

        btn_run = QPushButton("▶  Run All")
        btn_run.setObjectName("primaryBtn")
        btn_run.clicked.connect(self._run_all)
        toolbar.addWidget(btn_run)

        btn_run_sel = QPushButton("▶  Run Selected")
        btn_run_sel.clicked.connect(self._run_selected)
        toolbar.addWidget(btn_run_sel)

        btn_undo = QPushButton("↩  Undo All")
        btn_undo.setObjectName("dangerBtn")
        btn_undo.clicked.connect(self._undo_all)
        toolbar.addWidget(btn_undo)

        btn_clear = QPushButton("✕  Clear List")
        btn_clear.clicked.connect(self._clear_list)
        toolbar.addWidget(btn_clear)

        toolbar.addStretch()

        btn_settings = QPushButton("⚙")
        btn_settings.setObjectName("settingsToolbarButton")
        btn_settings.setFixedWidth(40)
        btn_settings.clicked.connect(self._open_settings)
        toolbar.addWidget(btn_settings)

        root.addWidget(toolbar_frame)

        # ── Non-admin warning banner ───────────────────────────
        self._admin_banner = QFrame()
        self._admin_banner.setObjectName("adminBanner")
        self._admin_banner.setStyleSheet(
            "QFrame#adminBanner { background: #3b2a00; border-bottom: 1px solid #7a5500; }"
        )
        banner_layout = QHBoxLayout(self._admin_banner)
        banner_layout.setContentsMargins(10, 5, 10, 5)
        banner_layout.setSpacing(10)

        warn_icon = QLabel("⚠")
        warn_icon.setStyleSheet("color: #fbbf24; font-size: 15px;")
        banner_layout.addWidget(warn_icon)

        warn_text = QLabel(
            "Not running as Administrator — icon changes may fail on protected folders."
        )
        warn_text.setStyleSheet("color: #fde68a; font-size: 12px;")
        banner_layout.addWidget(warn_text, 1)

        btn_elevate = QPushButton("Restart as Administrator")
        btn_elevate.setStyleSheet(
            "QPushButton { background: #7a5500; color: #fde68a; border: 1px solid #a07000;"
            " border-radius: 5px; padding: 3px 10px; min-height: 24px; }"
            "QPushButton:hover { background: #a07000; color: #ffffff; }"
        )
        btn_elevate.clicked.connect(self._restart_as_admin)
        banner_layout.addWidget(btn_elevate)

        self._admin_banner.setVisible(not self._is_admin)
        root.addWidget(self._admin_banner)

        # ── No API keys warning banner ─────────────────────────
        self._api_key_banner = QFrame()
        self._api_key_banner.setObjectName("apiKeyBanner")
        self._api_key_banner.setStyleSheet(
            "QFrame#apiKeyBanner { background: #0e0a20; border-bottom: 1px solid #4a3a8a; }"
        )
        api_banner_layout = QHBoxLayout(self._api_key_banner)
        api_banner_layout.setContentsMargins(10, 5, 10, 5)
        api_banner_layout.setSpacing(10)

        api_icon = QLabel("🔑")
        api_icon.setStyleSheet("color: #818cf8; font-size: 15px; background: transparent;")
        api_banner_layout.addWidget(api_icon)

        api_text = QLabel(
            "No API keys configured — Movies, TV & Game searches will return no results."
        )
        api_text.setStyleSheet(
            "color: #a5b4fc; font-size: 12px; background: transparent;"
        )
        api_banner_layout.addWidget(api_text, 1)

        btn_setup_keys = QPushButton("Open Settings to Add Keys")
        btn_setup_keys.setStyleSheet(
            "QPushButton { background: #2d1f5e; color: #a5b4fc; border: 1px solid #4a3a8a;"
            " border-radius: 5px; padding: 3px 10px; min-height: 24px; }"
            "QPushButton:hover { background: #4a3a8a; color: #ffffff; }"
        )
        btn_setup_keys.clicked.connect(self._open_settings)
        api_banner_layout.addWidget(btn_setup_keys)

        self._api_key_banner.setVisible(self._any_api_key_missing())
        root.addWidget(self._api_key_banner)

        # ── Content area (padded) ──────────────────────────────
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 4)
        content_layout.setSpacing(6)

        # Main splitter: table | preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Folder table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Folder", "Type", "Best Match", "Conf.", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.doubleClicked.connect(self._on_double_click)
        splitter.addWidget(self._table)

        # Right panel: preview + action buttons
        right = QFrame()
        right.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 4, 8)
        right_layout.setSpacing(8)

        self._preview = PreviewWidget()
        right_layout.addWidget(self._preview)

        btn_apply = QPushButton("✓  Apply This Icon")
        btn_apply.setObjectName("primaryBtn")
        btn_apply.clicked.connect(self._apply_selected_row)
        right_layout.addWidget(btn_apply)

        btn_skip = QPushButton("Skip")
        btn_skip.clicked.connect(self._skip_selected_row)
        right_layout.addWidget(btn_skip)

        btn_search_again = QPushButton("Search Again…")
        btn_search_again.clicked.connect(self._search_again)
        right_layout.addWidget(btn_search_again)

        btn_undo_one = QPushButton("↩  Undo This Folder")
        btn_undo_one.setObjectName("dangerBtn")
        btn_undo_one.clicked.connect(self._undo_selected_row)
        right_layout.addWidget(btn_undo_one)

        right_layout.addStretch()
        right.setMinimumWidth(260)
        right.setMaximumWidth(320)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        content_layout.addWidget(splitter)
        root.addWidget(content, 1)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(200)
        self._progress.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress)
        self._status_bar.showMessage("Ready")

    # ── Folder management ──────────────────────────────────────

    def _pick_folders(self):
        folders = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folders:
            self._add_folder(folders)

    def _pick_parent(self):
        parent = QFileDialog.getExistingDirectory(self, "Select Parent Directory")
        if not parent:
            return
        try:
            for name in sorted(os.listdir(parent)):
                full = os.path.join(parent, name)
                if os.path.isdir(full):
                    self._add_folder(full)
        except Exception:
            pass

    def _add_folder(self, path: str):
        if any(e.path == path for e in self._entries):
            return
        entry = FolderEntry(path=path, name=os.path.basename(path))
        row = len(self._entries)
        self._entries.append(entry)
        self._table.insertRow(row)
        self._table.setItem(row, _COL_NAME, QTableWidgetItem(entry.name))
        self._table.setItem(row, _COL_TYPE, QTableWidgetItem("—"))
        self._table.setItem(row, _COL_MATCH, QTableWidgetItem("—"))
        self._table.setItem(row, _COL_CONF, QTableWidgetItem("—"))
        self._set_status_cell(row, _STATUS_PENDING)

    def _clear_list(self):
        self._entries.clear()
        self._table.setRowCount(0)
        self._preview.show_result(None)

    # ── Processing ─────────────────────────────────────────────

    def _run_all(self):
        rows = range(len(self._entries))
        self._run_rows(list(rows))

    def _run_selected(self):
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        self._run_rows(rows)

    def _run_rows(self, rows: List[int]):
        pending = [r for r in rows if not self._entries[r].applied]
        if not pending:
            return
        self._pending_count = len(pending)
        self._progress.setMaximum(len(pending))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._status_bar.showMessage(f"Processing {len(pending)} folders…")
        for row in pending:
            self._set_status_cell(row, _STATUS_SEARCHING)
            w = _ProcessWorker(row, self._entries[row])
            w.done.connect(self._on_process_done)
            self._workers.append(w)
            w.start()

    def _on_process_done(self, row: int, detection: DetectionResult, results: List[SearchResult]):
        entry = self._entries[row]
        entry.detection = detection
        entry.results = results
        if results:
            entry.selected_result = results[0]

        self._table.item(row, _COL_TYPE).setText(detection.content_type.value)
        if results:
            r = results[0]
            self._table.item(row, _COL_MATCH).setText(r.title)
            self._table.item(row, _COL_CONF).setText(f"{r.confidence:.0f}%")
            self._set_status_cell(row, _STATUS_READY)
        else:
            self._table.item(row, _COL_MATCH).setText("No results")
            self._table.item(row, _COL_CONF).setText("—")
            self._set_status_cell(row, _STATUS_SKIPPED)
            missing = get_missing_keys_info(detection.content_type)
            if missing:
                labels = ", ".join(m["label"].split("  (")[0] for m in missing)
                self._status_bar.showMessage(
                    f"Skipped \"{entry.name}\" — missing API key: {labels}. "
                    "Open ⚙ Settings to add credentials.",
                    10000,
                )

        prefs = load_prefs()
        threshold = prefs.get("auto_apply_threshold", 85)
        if results and results[0].confidence >= threshold:
            self._apply_row(row)
        else:
            self._advance_progress()

        if row == self._table.currentRow():
            self._preview.show_result(entry.selected_result)

    def _apply_row(self, row: int):
        self._set_status_cell(row, _STATUS_APPLYING)
        w = _ApplyWorker(row, self._entries[row])
        w.done.connect(self._on_apply_done)
        self._workers.append(w)
        w.start()

    def _on_apply_done(self, row: int, success: bool, error_msg: str):
        self._entries[row].applied = success
        self._set_status_cell(row, _STATUS_DONE if success else _STATUS_FAILED)
        if not success and error_msg:
            is_permission = "permission" in error_msg.lower() or "access" in error_msg.lower()
            tip = " — try restarting as Administrator (⚠ banner above)" if is_permission else ""
            self._status_bar.showMessage(
                f"Failed: {self._entries[row].name} — {error_msg}{tip}", 8000
            )
        self._advance_progress()

    def _advance_progress(self):
        self._progress.setValue(self._progress.value() + 1)
        if self._progress.value() >= self._progress.maximum():
            self._progress.setVisible(False)
            self._status_bar.showMessage("Done.")

    # ── Row actions ────────────────────────────────────────────

    def _on_selection_changed(self):
        self._on_row_changed(self._table.currentRow())

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._entries):
            self._preview.show_result(self._entries[row].selected_result)

    def _on_double_click(self, index: QModelIndex):
        self._search_again()

    def _apply_selected_row(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._entries):
            self._apply_row(row)

    def _skip_selected_row(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._entries):
            self._set_status_cell(row, _STATUS_SKIPPED)

    def _undo_selected_row(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._entries):
            entry = self._entries[row]
            ok = icon_applier.undo(entry.path)
            if ok:
                entry.applied = False
                self._set_status_cell(row, _STATUS_PENDING)
            else:
                QMessageBox.warning(self, "Undo failed", f"Could not undo icon for:\n{entry.path}")

    def _undo_all(self):
        for i, entry in enumerate(self._entries):
            if entry.applied:
                icon_applier.undo(entry.path)
                entry.applied = False
                self._set_status_cell(i, _STATUS_PENDING)
        self._status_bar.showMessage("All icons reverted.")

    def _search_again(self):
        row = self._table.currentRow()
        if not (0 <= row < len(self._entries)):
            return
        entry = self._entries[row]
        det = entry.detection
        dlg = SearchDialog(
            initial_query=det.clean_title if det else entry.name,
            initial_type=det.content_type if det else ContentType.UNKNOWN,
            parent=self,
        )
        if dlg.exec() and dlg.selected:
            entry.selected_result = dlg.selected
            self._table.item(row, _COL_MATCH).setText(dlg.selected.title)
            self._table.item(row, _COL_CONF).setText(f"{dlg.selected.confidence:.0f}%")
            self._set_status_cell(row, _STATUS_READY)
            self._preview.show_result(dlg.selected)

    # ── Admin elevation ────────────────────────────────────────

    def _restart_as_admin(self):
        import sys
        script = os.path.abspath(sys.argv[0])
        extra = " ".join(f'"{a}"' for a in sys.argv[1:])
        params = f'"{script}"' if not extra else f'"{script}" {extra}'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        import sys as _sys
        _sys.exit(0)

    # ── Settings ───────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._prefs = load_prefs()
            self._refresh_api_key_banner()

    # ── API key banner helpers ─────────────────────────────────

    @staticmethod
    def _any_api_key_missing() -> bool:
        from app.services.detector import ContentType
        return bool(get_missing_keys_info(ContentType.UNKNOWN))

    def _refresh_api_key_banner(self):
        self._api_key_banner.setVisible(self._any_api_key_missing())

    # ── Helpers ────────────────────────────────────────────────

    def _set_status_cell(self, row: int, status: str):
        item = self._table.item(row, _COL_STATUS)
        if item is None:
            item = QTableWidgetItem()
            self._table.setItem(row, _COL_STATUS, item)
        item.setText(status)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # (foreground, subtle background tint) pairs per status
        color_map = {
            _STATUS_PENDING:   ("#5a5a80", "#101018"),
            _STATUS_SEARCHING: ("#60a5fa", "#0d1a2e"),
            _STATUS_READY:     ("#fbbf24", "#1e180a"),
            _STATUS_APPLYING:  ("#818cf8", "#0f0f22"),
            _STATUS_DONE:      ("#4ade80", "#0a1c0f"),
            _STATUS_FAILED:    ("#f87171", "#1c0a0a"),
            _STATUS_SKIPPED:   ("#4a4a68", "#0e0e16"),
        }
        fg, bg = color_map.get(status, ("#c8c8e8", "#0d0d12"))
        item.setForeground(QBrush(QColor(fg)))
        item.setBackground(QBrush(QColor(bg)))
