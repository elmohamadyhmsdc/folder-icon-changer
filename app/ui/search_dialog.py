from typing import Optional, List

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QComboBox, QLabel, QDialogButtonBox,
)

from app.services.detector import ContentType
from app.services.searcher import SearchResult, search_for
from app.ui.preview_widget import PreviewWidget


class _SearchWorker(QThread):
    results_ready = pyqtSignal(list)

    def __init__(self, query: str, content_type: ContentType):
        super().__init__()
        self.query = query
        self.content_type = content_type

    def run(self):
        results = search_for(self.query, self.content_type)
        self.results_ready.emit(results)


class SearchDialog(QDialog):
    """
    Manual search override dialog. User can type a custom query,
    pick the content type, and select a result.
    """

    def __init__(self, initial_query: str, initial_type: ContentType, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Override")
        self.setMinimumSize(700, 500)
        self._results: List[SearchResult] = []
        self.selected: Optional[SearchResult] = None
        self._worker: Optional[_SearchWorker] = None
        self._build_ui(initial_query, initial_type)

    def _build_ui(self, query: str, content_type: ContentType):
        layout = QVBoxLayout(self)

        # Search bar row
        row = QHBoxLayout()
        self._query_edit = QLineEdit(query)
        self._query_edit.setPlaceholderText("Title to search…")
        self._query_edit.returnPressed.connect(self._do_search)
        row.addWidget(self._query_edit, stretch=3)

        self._type_combo = QComboBox()
        for ct in ContentType:
            self._type_combo.addItem(ct.value, ct)
        self._type_combo.setCurrentIndex(list(ContentType).index(content_type))
        row.addWidget(self._type_combo, stretch=1)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._do_search)
        row.addWidget(search_btn)
        layout.addLayout(row)

        # Body: results list + preview
        body = QHBoxLayout()

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        body.addWidget(self._list, stretch=2)

        self._preview = PreviewWidget()
        self._preview.setMinimumWidth(240)
        body.addWidget(self._preview, stretch=1)

        layout.addLayout(body)

        self._status = QLabel("Enter a query and press Search.")
        self._status.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self._status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _do_search(self):
        query = self._query_edit.text().strip()
        if not query:
            return
        ct = self._type_combo.currentData()
        self._status.setText("Searching…")
        self._list.clear()
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self._worker = _SearchWorker(query, ct)
        self._worker.results_ready.connect(self._on_results)
        self._worker.start()

    def _on_results(self, results: List[SearchResult]):
        self._results = results
        self._list.clear()
        if not results:
            self._status.setText("No results found.")
            return
        for r in results:
            label = f"{r.title}  ({r.year})  ★{r.score or '?'}  [{r.confidence:.0f}%]"
            self._list.addItem(QListWidgetItem(label))
        self._list.setCurrentRow(0)
        self._status.setText(f"{len(results)} results found.")

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._results):
            self._preview.show_result(self._results[row])

    def _accept(self):
        row = self._list.currentRow()
        if 0 <= row < len(self._results):
            self.selected = self._results[row]
        self.accept()
