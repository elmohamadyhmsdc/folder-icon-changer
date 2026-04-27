from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QCheckBox, QComboBox, QSpinBox, QDialogButtonBox,
    QLabel, QTabWidget, QWidget,
)
from PyQt6.QtCore import Qt

from app.config import get_api_key, set_api_key, load_prefs, save_prefs


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        if parent is not None:
            self.setStyleSheet(parent.styleSheet())
        self._prefs = load_prefs()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(self._build_api_tab(), "API Keys")
        tabs.addTab(self._build_icon_tab(), "Icon Style")
        tabs.addTab(self._build_behavior_tab(), "Behavior")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── API Keys tab ───────────────────────────────────────────

    def _build_api_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(10)
        form.setHorizontalSpacing(12)

        self._tmdb_key = QLineEdit(get_api_key("tmdb"))
        self._tmdb_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._tmdb_key.setPlaceholderText("Required for movies & TV shows")
        form.addRow("TMDB API Key:", self._tmdb_key)

        self._igdb_id = QLineEdit(get_api_key("igdb_client_id"))
        self._igdb_id.setPlaceholderText("Twitch App Client ID")
        form.addRow("IGDB Client ID:", self._igdb_id)

        self._igdb_secret = QLineEdit(get_api_key("igdb_client_secret"))
        self._igdb_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._igdb_secret.setPlaceholderText("Twitch App Client Secret")
        form.addRow("IGDB Client Secret:", self._igdb_secret)

        note = QLabel(
            "AniList (anime) requires no API key.\n"
            "TMDB key: themoviedb.org  |  IGDB: dev.twitch.tv"
        )
        note.setStyleSheet(
            "color: #7070a0;"
            " font-size: 11px;"
            " background: #13131a;"
            " border: 1px solid #1e1e2e;"
            " border-radius: 5px;"
            " padding: 8px 10px;"
        )
        form.addRow(note)
        return w

    # ── Icon Style tab ─────────────────────────────────────────

    def _build_icon_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(10)
        form.setHorizontalSpacing(12)

        self._style_combo = QComboBox()
        styles = [
            ("clean_poster", "Clean Poster"),
            ("framed", "Framed"),
            ("glassmorphism", "Glassmorphism"),
            ("rating_badge", "Rating Badge"),
            ("minimal", "Minimal"),
        ]
        for val, label in styles:
            self._style_combo.addItem(label, val)
        current = self._prefs.get("icon_style", "clean_poster")
        idx = next((i for i, (v, _) in enumerate(styles) if v == current), 0)
        self._style_combo.setCurrentIndex(idx)
        form.addRow("Icon style:", self._style_combo)

        self._rounded = QCheckBox("Rounded corners")
        self._rounded.setChecked(self._prefs.get("rounded_corners", True))
        form.addRow(self._rounded)

        self._radius_spin = QSpinBox()
        self._radius_spin.setRange(0, 64)
        self._radius_spin.setValue(self._prefs.get("corner_radius", 12))
        form.addRow("Corner radius:", self._radius_spin)

        self._badge_check = QCheckBox("Show rating badge on icon")
        self._badge_check.setChecked(self._prefs.get("show_rating_badge", False))
        form.addRow(self._badge_check)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(128, 512)
        self._size_spin.setSingleStep(64)
        self._size_spin.setValue(self._prefs.get("icon_size", 256))
        form.addRow("Icon resolution (px):", self._size_spin)

        return w

    # ── Behavior tab ───────────────────────────────────────────

    def _build_behavior_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 16, 12, 12)
        form.setSpacing(10)
        form.setHorizontalSpacing(12)

        self._upscale_check = QCheckBox("AI upscale low-res anime images (waifu2x)")
        self._upscale_check.setChecked(self._prefs.get("upscale_anime", True))
        form.addRow(self._upscale_check)

        self._threshold_spin = QSpinBox()
        self._threshold_spin.setRange(50, 100)
        self._threshold_spin.setSuffix("%")
        self._threshold_spin.setValue(self._prefs.get("auto_apply_threshold", 85))
        form.addRow("Auto-apply threshold:", self._threshold_spin)

        note = QLabel(
            "Folders with match confidence above this threshold are applied automatically."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #7070a0;"
            " font-size: 11px;"
            " background: #13131a;"
            " border: 1px solid #1e1e2e;"
            " border-radius: 5px;"
            " padding: 8px 10px;"
        )
        form.addRow(note)

        self._dark_check = QCheckBox("Dark mode")
        self._dark_check.setChecked(self._prefs.get("dark_mode", True))
        form.addRow(self._dark_check)

        return w

    def _save(self):
        set_api_key("tmdb", self._tmdb_key.text().strip())
        set_api_key("igdb_client_id", self._igdb_id.text().strip())
        set_api_key("igdb_client_secret", self._igdb_secret.text().strip())

        self._prefs.update({
            "icon_style": self._style_combo.currentData(),
            "rounded_corners": self._rounded.isChecked(),
            "corner_radius": self._radius_spin.value(),
            "show_rating_badge": self._badge_check.isChecked(),
            "icon_size": self._size_spin.value(),
            "upscale_anime": self._upscale_check.isChecked(),
            "auto_apply_threshold": self._threshold_spin.value(),
            "dark_mode": self._dark_check.isChecked(),
        })
        save_prefs(self._prefs)
        self.accept()
