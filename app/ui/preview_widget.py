import io
from typing import Optional

import requests
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget, QSizePolicy

from app.services.searcher import SearchResult


class _ImageLoader(QThread):
    loaded = pyqtSignal(bytes)
    failed = pyqtSignal()

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            resp = requests.get(self.url, timeout=15)
            resp.raise_for_status()
            self.loaded.emit(resp.content)
        except Exception:
            self.failed.emit()


class PreviewWidget(QWidget):
    """Shows a live icon preview for the selected search result."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader: Optional[_ImageLoader] = None
        self._result: Optional[SearchResult] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(220, 220)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet(
            "background: #1e1e1e; border-radius: 12px; border: 1px solid #333;"
        )
        layout.addWidget(self._icon_label)

        self._title_label = QLabel("—")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #eee;")
        layout.addWidget(self._title_label)

        self._meta_label = QLabel("")
        self._meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._meta_label.setStyleSheet("font-size: 11px; color: #aaa;")
        layout.addWidget(self._meta_label)

        self._source_label = QLabel("")
        self._source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source_label.setStyleSheet("font-size: 10px; color: #666;")
        layout.addWidget(self._source_label)

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
            meta_parts.append(f"★ {result.score}")
        self._meta_label.setText("  •  ".join(meta_parts))
        self._source_label.setText(f"via {result.source}  •  {result.confidence:.0f}% match")

        if result.image_url:
            self._load_image(result.image_url)
        else:
            self._show_placeholder()

    def _clear(self):
        self._icon_label.setText("No selection")
        self._icon_label.setPixmap(QPixmap())
        self._title_label.setText("—")
        self._meta_label.setText("")
        self._source_label.setText("")

    def _load_image(self, url: str):
        if self._loader and self._loader.isRunning():
            self._loader.terminate()
        self._loader = _ImageLoader(url)
        self._loader.loaded.connect(self._on_image_loaded)
        self._loader.failed.connect(self._show_placeholder)
        self._icon_label.setText("Loading…")
        self._loader.start()

    def _on_image_loaded(self, data: bytes):
        try:
            from PIL import ImageFilter
            size = 220
            src = Image.open(io.BytesIO(data)).convert("RGBA")
            w, h = src.size

            # Background: cover-scale → heavy blur → darken
            bg_scale = max(size / w, size / h)
            bg_w, bg_h = int(w * bg_scale), int(h * bg_scale)
            bg = src.resize((bg_w, bg_h), Image.LANCZOS)
            bx = (bg_w - size) // 2
            by = (bg_h - size) // 2
            bg = bg.crop((bx, by, bx + size, by + size))
            bg = bg.filter(ImageFilter.GaussianBlur(radius=18))
            r, g, b, a = bg.split()
            darken = 0.5
            r = r.point(lambda x: int(x * darken))
            g = g.point(lambda x: int(x * darken))
            b = b.point(lambda x: int(x * darken))
            bg = Image.merge("RGBA", (r, g, b, a))

            # Foreground: contain-scale, slight upward bias
            fg_scale = min(size / w, size / h)
            fg_w, fg_h = int(w * fg_scale), int(h * fg_scale)
            fg = src.resize((fg_w, fg_h), Image.LANCZOS)
            paste_x = (size - fg_w) // 2
            paste_y = int((size - fg_h) * 0.30)
            bg.paste(fg, (paste_x, paste_y), fg)

            pil_img = bg

            # Rounded corners preview
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (size - 1, size - 1)], radius=14, fill=255)
            pil_img.putalpha(mask)

            raw = pil_img.tobytes("raw", "RGBA")
            qimg = QImage(raw, size, size, QImage.Format.Format_RGBA8888)
            self._icon_label.setPixmap(QPixmap.fromImage(qimg))
        except Exception:
            self._show_placeholder()

    def _show_placeholder(self):
        self._icon_label.setText("No image")
        self._icon_label.setPixmap(QPixmap())
