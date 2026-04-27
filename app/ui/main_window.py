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
    QAbstractItemView, QMessageBox,
)

from app.config import load_prefs
from app.services.detector import detect, ContentType, DetectionResult
from app.services.searcher import SearchResult, search_for
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
    done = pyqtSignal(int, bool)  # row_idx, success

    def __init__(self, row: int, entry: FolderEntry):
        super().__init__()
        self.row = row
        self.entry = entry

    def run(self):
        result = self.entry.selected_result
        if result is None or not result.image_url:
            self.done.emit(self.row, False)
            return
        with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as f:
            ico_path = f.name
        try:
            ok = build_ico(
                result.image_url,
                ico_path,
                content_type=ContentType(self.entry.detection.content_type) if self.entry.detection else ContentType.UNKNOWN,
                score=result.score,
            )
            if ok:
                ok = icon_applier.apply(self.entry.path, ico_path)
        finally:
            if os.path.exists(ico_path):
                os.remove(ico_path)
        self.done.emit(self.row, ok)


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
QMainWindow, QWidget { background: #1a1a1a; color: #e0e0e0; }
QTableWidget { background: #222; gridline-color: #333; color: #ddd; }
QTableWidget::item:selected { background: #3a3a6a; }
QHeaderView::section { background: #2a2a2a; color: #aaa; border: 1px solid #333; padding: 4px; }
QPushButton { background: #2d2d2d; color: #ddd; border: 1px solid #444; border-radius: 4px; padding: 5px 12px; }
QPushButton:hover { background: #3a3a3a; }
QPushButton:disabled { color: #555; }
QLineEdit, QComboBox, QSpinBox { background: #2a2a2a; color: #ddd; border: 1px solid #444; border-radius: 3px; padding: 3px; }
QStatusBar { background: #222; color: #888; }
QProgressBar { background: #2a2a2a; border: 1px solid #444; border-radius: 3px; text-align: center; color: #ccc; }
QProgressBar::chunk { background: #4a6fa5; border-radius: 2px; }
QSplitter::handle { background: #333; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._prefs = load_prefs()
        self._entries: List[FolderEntry] = []
        self._workers: List[QThread] = []
        self._pending_count = 0
        self._setup_ui()
        if self._prefs.get("dark_mode", True):
            self.setStyleSheet(_DARK_STYLE)

    def _setup_ui(self):
        self.setWindowTitle("Folder Icon Changer")
        self.setMinimumSize(1000, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        btn_folder = QPushButton("+ Add Folder(s)")
        btn_folder.clicked.connect(self._pick_folders)
        toolbar.addWidget(btn_folder)

        btn_parent = QPushButton("+ Add All Subfolders…")
        btn_parent.clicked.connect(self._pick_parent)
        toolbar.addWidget(btn_parent)

        toolbar.addStretch()

        btn_run = QPushButton("▶  Run All")
        btn_run.clicked.connect(self._run_all)
        toolbar.addWidget(btn_run)

        btn_run_sel = QPushButton("▶  Run Selected")
        btn_run_sel.clicked.connect(self._run_selected)
        toolbar.addWidget(btn_run_sel)

        btn_undo = QPushButton("↩  Undo All")
        btn_undo.clicked.connect(self._undo_all)
        toolbar.addWidget(btn_undo)

        btn_clear = QPushButton("✕  Clear List")
        btn_clear.clicked.connect(self._clear_list)
        toolbar.addWidget(btn_clear)

        btn_settings = QPushButton("⚙")
        btn_settings.setFixedWidth(32)
        btn_settings.clicked.connect(self._open_settings)
        toolbar.addWidget(btn_settings)

        root.addLayout(toolbar)

        # Main splitter: table | preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Folder", "Type", "Best Match", "Conf.", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.currentRowChanged.connect(self._on_row_changed)
        self._table.doubleClicked.connect(self._on_double_click)
        splitter.addWidget(self._table)

        # Right panel: preview + action buttons
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)

        self._preview = PreviewWidget()
        right_layout.addWidget(self._preview)

        btn_apply = QPushButton("✓  Apply This Icon")
        btn_apply.clicked.connect(self._apply_selected_row)
        right_layout.addWidget(btn_apply)

        btn_skip = QPushButton("Skip")
        btn_skip.clicked.connect(self._skip_selected_row)
        right_layout.addWidget(btn_skip)

        btn_search_again = QPushButton("Search Again…")
        btn_search_again.clicked.connect(self._search_again)
        right_layout.addWidget(btn_search_again)

        btn_undo_one = QPushButton("↩  Undo This Folder")
        btn_undo_one.clicked.connect(self._undo_selected_row)
        right_layout.addWidget(btn_undo_one)

        right_layout.addStretch()
        right.setMinimumWidth(260)
        right.setMaximumWidth(320)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(200)
        self._progress.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress)
        self._status_bar.showMessage("Ready")

    # --- Folder management ---

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

    # --- Processing ---

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

        # Auto-apply if confidence is high enough
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

    def _on_apply_done(self, row: int, success: bool):
        self._entries[row].applied = success
        self._set_status_cell(row, _STATUS_DONE if success else _STATUS_FAILED)
        self._advance_progress()

    def _advance_progress(self):
        self._progress.setValue(self._progress.value() + 1)
        if self._progress.value() >= self._progress.maximum():
            self._progress.setVisible(False)
            self._status_bar.showMessage("Done.")

    # --- Row actions ---

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

    # --- Settings ---

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._prefs = load_prefs()
            if self._prefs.get("dark_mode", True):
                self.setStyleSheet(_DARK_STYLE)
            else:
                self.setStyleSheet("")

    # --- Helpers ---

    def _set_status_cell(self, row: int, status: str):
        item = self._table.item(row, _COL_STATUS)
        if item is None:
            item = QTableWidgetItem()
            self._table.setItem(row, _COL_STATUS, item)
        item.setText(status)
        color_map = {
            _STATUS_PENDING: "#555",
            _STATUS_SEARCHING: "#4a90e2",
            _STATUS_READY: "#e2a84a",
            _STATUS_APPLYING: "#4a90e2",
            _STATUS_DONE: "#4caf50",
            _STATUS_FAILED: "#e25c4a",
            _STATUS_SKIPPED: "#777",
        }
        fg = color_map.get(status, "#ccc")
        item.setForeground(QBrush(QColor(fg)))
