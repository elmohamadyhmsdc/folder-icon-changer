import webbrowser
from typing import Optional, List

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QComboBox, QLabel, QDialogButtonBox,
    QFrame,
)

from app.services.detector import ContentType
from app.services.searcher import SearchResult, search_for, get_missing_keys_info
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
        self.setMinimumSize(750, 520)
        if parent is not None:
            self.setStyleSheet(parent.styleSheet())
        self._results: List[SearchResult] = []
        self.selected: Optional[SearchResult] = None
        self._worker: Optional[_SearchWorker] = None
        self._build_ui(initial_query, initial_type)

    def _build_ui(self, query: str, content_type: ContentType):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Search bar row
        row = QHBoxLayout()
        row.setSpacing(8)
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
        search_btn.setObjectName("primaryBtn")
        search_btn.clicked.connect(self._do_search)
        row.addWidget(search_btn)
        layout.addLayout(row)

        # API key guidance banner (hidden until needed)
        self._api_banner = self._build_api_banner()
        self._api_banner.setVisible(False)
        layout.addWidget(self._api_banner)

        # Body: results list + preview
        body = QHBoxLayout()
        body.setSpacing(10)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        body.addWidget(self._list, stretch=2)

        self._preview = PreviewWidget()
        self._preview.setMinimumWidth(260)
        body.addWidget(self._preview, stretch=1)

        layout.addLayout(body)

        self._status = QLabel("Enter a query and press Search.")
        self._status.setStyleSheet(
            "color: #6060a0; font-size: 11px; background: transparent;"
        )
        layout.addWidget(self._status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── API key banner ──────────────────────────────────────────

    def _build_api_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("apiKeyBanner")
        banner.setStyleSheet(
            "QFrame#apiKeyBanner {"
            " background: #1a1000;"
            " border: 1px solid #7a5500;"
            " border-radius: 6px;"
            "}"
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        icon_lbl = QLabel("🔑")
        icon_lbl.setStyleSheet(
            "background: transparent; border: none; font-size: 18px;"
        )
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        self._banner_title = QLabel("API key required to search this content type")
        self._banner_title.setStyleSheet(
            "background: transparent; border: none;"
            " font-weight: bold; font-size: 12px; color: #fde68a;"
        )
        text_col.addWidget(self._banner_title)

        self._banner_body = QLabel()
        self._banner_body.setWordWrap(True)
        self._banner_body.setStyleSheet(
            "background: transparent; border: none;"
            " font-size: 11px; color: #d4b483;"
        )
        text_col.addWidget(self._banner_body)

        self._banner_links = QLabel()
        self._banner_links.setOpenExternalLinks(True)
        self._banner_links.setWordWrap(True)
        self._banner_links.setStyleSheet(
            "background: transparent; border: none;"
            " font-size: 11px; color: #818cf8;"
        )
        text_col.addWidget(self._banner_links)

        layout.addLayout(text_col, stretch=1)

        btn_settings = QPushButton("Open Settings")
        btn_settings.setStyleSheet(
            "QPushButton {"
            " background: #3a2800; color: #fde68a;"
            " border: 1px solid #7a5500; border-radius: 5px;"
            " padding: 4px 12px; min-height: 26px; font-size: 11px;"
            "}"
            "QPushButton:hover { background: #7a5500; color: #ffffff; }"
        )
        btn_settings.clicked.connect(self._open_settings_from_banner)
        layout.addWidget(btn_settings)

        return banner

    def _open_settings_from_banner(self):
        from app.ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        if dlg.exec():
            # Keys may have changed — re-run the last search automatically
            self._do_search()

    def _update_api_banner(self, missing: List[dict]):
        """Populate and show the banner for the given list of missing key infos."""
        if not missing:
            self._api_banner.setVisible(False)
            return

        labels = "  •  ".join(m["label"] for m in missing)
        self._banner_title.setText(
            f"API key{'s' if len(missing) > 1 else ''} required — no results can be returned"
        )
        self._banner_body.setText(
            f"Missing: {labels}\n"
            "Add your credentials in Settings, then search again."
        )

        link_parts = []
        for m in missing:
            link_parts.append(
                f'<a href="{m["signup_url"]}" style="color:#818cf8;">Create {m["service"].upper()} account</a>'
                f' &nbsp;·&nbsp; '
                f'<a href="{m["url"]}" style="color:#818cf8;">Get API key</a>'
            )
        self._banner_links.setText("  |  ".join(link_parts))
        self._api_banner.setVisible(True)

    # ── Search ──────────────────────────────────────────────────

    def _do_search(self):
        query = self._query_edit.text().strip()
        if not query:
            return
        ct = self._type_combo.currentData()
        self._status.setText("Searching…")
        self._list.clear()
        self._api_banner.setVisible(False)
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self._worker = _SearchWorker(query, ct)
        self._worker.results_ready.connect(self._on_results)
        self._worker.start()

    def _on_results(self, results: List[SearchResult]):
        self._results = results
        self._list.clear()
        if not results:
            ct = self._type_combo.currentData()
            missing = get_missing_keys_info(ct)
            if missing:
                self._update_api_banner(missing)
                self._status.setText("No results — API key required.")
            else:
                self._api_banner.setVisible(False)
                self._status.setText("No results found.")
            return

        self._api_banner.setVisible(False)
        for r in results:
            score_str = f"★ {r.score:.1f}" if r.score is not None else "★ ?"
            year_str = f"  ({r.year})" if r.year else ""
            line1 = f"{r.title or 'Unknown'}{year_str}"
            line2 = f"{score_str}   {r.source}   {r.confidence:.0f}% match"
            item = QListWidgetItem(f"{line1}\n{line2}")
            item.setSizeHint(QSize(0, 52))
            self._list.addItem(item)
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
