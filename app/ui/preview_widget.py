from typing import Optional

from PIL import Image
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.config import load_prefs
from app.services import image_pipeline
from app.services.searcher import SearchResult
from app.utils import threads

_PREVIEW_SIZE = 190


class _ImageLoader(QThread):
    """Downloads the poster and renders the *real* icon (same code as Apply)."""

    loaded = pyqtSignal(object, bytes)   # key, RGBA bytes (_PREVIEW_SIZE square)
    failed = pyqtSignal(object)          # key

    def __init__(self, key, url: str, score: Optional[float]):
        super().__init__()
        self.key = key
        self.url = url
        self.score = score

    def run(self):
        try:
            img = image_pipeline.download_image(self.url)
            if img is None:
                self.failed.emit(self.key)
                return
            # upscale=False keeps previews instant; the saved icon may be sharper.
            icon = image_pipeline.render_icon(img, score=self.score, prefs=load_prefs(), upscale=False)
            icon = icon.resize((_PREVIEW_SIZE, _PREVIEW_SIZE), Image.LANCZOS).convert("RGBA")
            self.loaded.emit(self.key, icon.tobytes("raw", "RGBA"))
        except Exception:
            self.failed.emit(self.key)


class PreviewWidget(QWidget):
    """Shows what the folder icon will look like for the selected result."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_key = None
        self._result: Optional[SearchResult] = None
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        card_layout.setContentsMargins(12, 14, 12, 14)
        card_layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(_PREVIEW_SIZE, _PREVIEW_SIZE)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet(
            "background: #0d0d12; border-radius: 12px; border: 1px dashed #2e2e48;"
            " color: #5a5a80; font-size: 12px;"
        )
        card_layout.addWidget(self._icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._title_label = QLabel("")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setWordWrap(True)
        self._title_label.setObjectName("h2")
        card_layout.addWidget(self._title_label)

        self._meta_label = QLabel("")
        self._meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._meta_label.setStyleSheet("color: #818cf8; font-size: 12px; background: transparent;")
        card_layout.addWidget(self._meta_label)

        self._source_label = QLabel("")
        self._source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source_label.setObjectName("hint")
        card_layout.addWidget(self._source_label)

        outer.addWidget(card)
        self._clear()

    # ── Public API ────────────────────────────────────────────

    def show_result(self, result: Optional[SearchResult]):
        self._result = result
        if result is None:
            self._clear()
            return

        self._title_label.setText(result.title or "Unknown")
        meta_parts = []
        if result.year:
            meta_parts.append(result.year)
        if result.score is not None:
            meta_parts.append(f"★ {result.score:.1f}")
        self._meta_label.setText("  •  ".join(meta_parts))
        self._source_label.setText(f"via {result.source}  •  {result.confidence:.0f}% match")

        if result.image_url:
            self._load_image(result.image_url, result.score)
        else:
            self._current_key = None
            self._show_message("This match has no artwork")

    def refresh(self):
        """Re-render with the current settings (call after Settings change)."""
        self.show_result(self._result)

    # ── Internals ─────────────────────────────────────────────

    def _clear(self):
        self._current_key = None
        self._show_message("Select a folder to\npreview its icon")
        self._title_label.setText("")
        self._meta_label.setText("")
        self._source_label.setText("")

    def _show_message(self, text: str):
        self._icon_label.setPixmap(QPixmap())
        self._icon_label.setText(text)

    def _load_image(self, url: str, score: Optional[float]):
        # Superseded downloads keep running but their result is ignored (keyed
        # by object identity of `key`), so nothing is ever terminate()d.
        key = object()
        self._current_key = key
        self._show_message("Loading…")
        loader = _ImageLoader(key, url, score)
        loader.loaded.connect(self._on_image_loaded)
        loader.failed.connect(self._on_image_failed)
        threads.start(loader)

    def _on_image_failed(self, key):
        if key is self._current_key:
            self._show_message("Couldn't load the artwork")

    def _on_image_loaded(self, key, raw: bytes):
        if key is not self._current_key:
            return
        qimg = QImage(raw, _PREVIEW_SIZE, _PREVIEW_SIZE, QImage.Format.Format_RGBA8888)
        self._icon_label.setText("")
        self._icon_label.setPixmap(QPixmap.fromImage(qimg))
