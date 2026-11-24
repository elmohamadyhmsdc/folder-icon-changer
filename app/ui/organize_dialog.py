import os
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from app.services import organizer
from app.services.organizer import MovieMove, OrganizeResult

_COL_FILE, _COL_FOLDER, _COL_NOTE = 0, 1, 2


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return ""


class OrganizeDialog(QDialog):
    """Preview-and-confirm dialog for moving loose movie files into folders."""

    def __init__(self, parent_dir: str, moves: List[MovieMove],
                 skipped: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Organize loose movies")
        self.setMinimumSize(860, 520)
        if parent is not None:
            self.setStyleSheet(parent.styleSheet())
        self._dir = parent_dir
        self._moves = moves
        self._skipped = skipped
        self._building = False
        self.result_info: Optional[OrganizeResult] = None
        self.find_icons_after = True
        self._build_ui()
        self._populate()

    # ── UI ────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        title = QLabel("Give each movie its own folder")
        title.setObjectName("h1")
        root.addWidget(title)

        intro = QLabel(
            f"These movie files sit directly in <b>{self._dir}</b>. A folder icon can only be set on "
            "a folder, so each movie will be moved (with its subtitles) into a folder named after it. "
            "Nothing is deleted or renamed, and you can undo this later from the ⋯ menu."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setObjectName("hint")
        root.addWidget(intro)

        bar = QHBoxLayout()
        self._count_label = QLabel("")
        self._count_label.setObjectName("h2")
        bar.addWidget(self._count_label)
        bar.addStretch()
        btn_all = QPushButton("Select all")
        btn_all.setObjectName("ghostBtn")
        btn_all.clicked.connect(lambda: self._set_all(True))
        bar.addWidget(btn_all)
        btn_none = QPushButton("Select none")
        btn_none.setObjectName("ghostBtn")
        btn_none.clicked.connect(lambda: self._set_all(False))
        bar.addWidget(btn_none)
        root.addLayout(bar)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Movie file", "New folder  (double-click to rename)", "Notes"])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(_COL_FILE, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(_COL_FOLDER, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(_COL_NOTE, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(34)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._table, 1)

        if self._skipped:
            names = "\n".join(f"{n}  —  {why}" for n, why in self._skipped)
            skipped = QLabel(f"{len(self._skipped)} other video file(s) will be left where they are (hover for details)")
            skipped.setObjectName("hint")
            skipped.setToolTip(names)
            root.addWidget(skipped)

        self._find_check = QCheckBox("Find and apply icons for these folders right after organizing")
        self._find_check.setChecked(True)
        root.addWidget(self._find_check)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self._ok = QPushButton("Organize")
        self._ok.setObjectName("primaryBtn")
        self._ok.setDefault(True)
        self._ok.clicked.connect(self._organize)
        row.addWidget(self._ok)
        root.addLayout(row)

    def _populate(self):
        self._building = True
        self._table.setRowCount(len(self._moves))
        for r, mv in enumerate(self._moves):
            file_item = QTableWidgetItem(f"{mv.filename}   ·   {_fmt_size(mv.size)}")
            file_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            file_item.setCheckState(Qt.CheckState.Checked if mv.selected else Qt.CheckState.Unchecked)
            file_item.setToolTip(mv.source)
            self._table.setItem(r, _COL_FILE, file_item)

            folder_item = QTableWidgetItem(mv.folder_name)
            folder_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(r, _COL_FOLDER, folder_item)

            note_item = QTableWidgetItem("")
            note_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._table.setItem(r, _COL_NOTE, note_item)
            self._paint_row(r)
        self._building = False
        self._update_summary()

    # ── State ─────────────────────────────────────────────────

    def _paint_row(self, r: int):
        mv = self._moves[r]
        note = self._table.item(r, _COL_NOTE)
        note.setText(mv.note)
        note.setForeground(QBrush(QColor("#f87171" if mv.blocked else "#8a8ab0")))
        folder = self._table.item(r, _COL_FOLDER)
        folder.setForeground(QBrush(QColor("#6a6a92" if mv.blocked else "#e4e4f2")))
        self._table.item(r, _COL_FILE).setForeground(QBrush(QColor("#6a6a92" if mv.blocked else "#d6d6ee")))

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._building:
            return
        r = item.row()
        mv = self._moves[r]
        if item.column() == _COL_FILE:
            mv.selected = item.checkState() == Qt.CheckState.Checked
        elif item.column() == _COL_FOLDER:
            clean = organizer.sanitize_folder_name(item.text())
            self._building = True
            item.setText(clean)
            self._building = False
            mv.folder_name = clean
            organizer.validate(mv, self._dir)
            self._paint_row(r)
        self._update_summary()

    def _set_all(self, checked: bool):
        self._building = True
        for r, mv in enumerate(self._moves):
            mv.selected = checked
            self._table.item(r, _COL_FILE).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._building = False
        self._update_summary()

    def _update_summary(self):
        # Two files that would land in the same new folder are fine (e.g. CD1/CD2),
        # but a blocked row can never be moved.
        n = sum(1 for m in self._moves if m.selected and not m.blocked)
        blocked = sum(1 for m in self._moves if m.blocked)
        text = f"{n} of {len(self._moves)} movies will be organized"
        if blocked:
            text += f"  ·  {blocked} need attention"
        self._count_label.setText(text)
        self._ok.setEnabled(n > 0)
        self._ok.setText(f"Organize {n} movie{'s' if n != 1 else ''}" if n else "Organize")

    # ── Action ────────────────────────────────────────────────

    def _organize(self):
        self.find_icons_after = self._find_check.isChecked()
        res = organizer.execute(self._moves, self._dir)
        self.result_info = res
        if res.errors:
            detail = "\n".join(f"• {n}: {e}" for n, e in res.errors[:8])
            QMessageBox.warning(
                self, "Some movies couldn't be moved",
                f"{res.moved} movie(s) were organized. These were left untouched:\n\n{detail}",
            )
        if res.moved == 0:
            self.reject()
        else:
            self.accept()
