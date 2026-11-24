from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from app.config import defaults, get_api_key, load_prefs, save_prefs, set_api_key
from app.services.detector import ContentType
from app.services.image_pipeline import render_icon

_STYLES = [
    ("clean_poster", "Clean Poster"),
    ("framed", "Framed"),
    ("glassmorphism", "Glassmorphism"),
    ("rating_badge", "Rating Badge"),
    ("minimal", "Minimal"),
]
_SAMPLE_SIZE = 150


def _sample_poster() -> Image.Image:
    """A synthetic 2:3 poster so style changes can be previewed without a download."""
    w, h = 300, 450
    img = Image.new("RGBA", (w, h))
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        c = (int(70 + 120 * t), int(60 + 20 * t), int(200 - 90 * t), 255)
        for x in range(w):
            px[x, y] = c
    d = ImageDraw.Draw(img)
    d.ellipse([(60, 90), (240, 270)], outline=(255, 255, 255, 200), width=6)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 40)
    except Exception:
        font = ImageFont.load_default()
    d.text((w // 2, 355), "SAMPLE", fill=(255, 255, 255, 235), font=font, anchor="mm")
    return img


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(580)
        if parent is not None:
            self.setStyleSheet(parent.styleSheet())
        self._prefs = load_prefs()
        self._poster = _sample_poster()
        self._build_ui()
        self._update_sample()

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
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.RestoreDefaults
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryBtn")
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText("Reset style && behavior")
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._restore_defaults)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── API Keys tab ───────────────────────────────────────────

    def _build_api_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(14, 18, 14, 12)
        form.setSpacing(10)
        form.setHorizontalSpacing(14)

        self._tmdb_key = QLineEdit(get_api_key("tmdb"))
        self._tmdb_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._tmdb_key.setPlaceholderText("Needed for movies & TV shows")
        form.addRow("TMDB API key:", self._tmdb_key)

        self._igdb_id = QLineEdit(get_api_key("igdb_client_id"))
        self._igdb_id.setPlaceholderText("Twitch app Client ID — needed for games")
        form.addRow("IGDB Client ID:", self._igdb_id)

        self._igdb_secret = QLineEdit(get_api_key("igdb_client_secret"))
        self._igdb_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._igdb_secret.setPlaceholderText("Twitch app Client Secret")
        form.addRow("IGDB Client Secret:", self._igdb_secret)

        show = QCheckBox("Show keys")
        show.toggled.connect(self._toggle_keys)
        form.addRow("", show)

        note = QLabel(
            "<b>Anime works without any key.</b> The keys below are free:<br>"
            "• TMDB (movies &amp; TV): <a href='https://www.themoviedb.org/settings/api' "
            "style='color:#818cf8;'>themoviedb.org/settings/api</a><br>"
            "• IGDB (games): <a href='https://dev.twitch.tv/console/apps' "
            "style='color:#818cf8;'>dev.twitch.tv/console/apps</a><br>"
            "Keys are stored in Windows Credential Manager, not in a file."
        )
        note.setOpenExternalLinks(True)
        note.setTextFormat(Qt.TextFormat.RichText)
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #8a8ab8; font-size: 11px; background: #13131a;"
            " border: 1px solid #1e1e2e; border-radius: 6px; padding: 10px 12px;"
        )
        form.addRow(note)
        return w

    def _toggle_keys(self, visible: bool):
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self._tmdb_key.setEchoMode(mode)
        self._igdb_secret.setEchoMode(mode)

    # ── Icon Style tab ─────────────────────────────────────────

    def _build_icon_tab(self) -> QWidget:
        w = QWidget()
        outer = QHBoxLayout(w)
        outer.setContentsMargins(14, 18, 14, 12)
        outer.setSpacing(18)

        form = QFormLayout()
        form.setSpacing(10)
        form.setHorizontalSpacing(14)

        self._style_combo = QComboBox()
        for val, label in _STYLES:
            self._style_combo.addItem(label, val)
        form.addRow("Icon style:", self._style_combo)

        self._rounded = QCheckBox("Rounded corners")
        form.addRow("", self._rounded)

        self._radius_spin = QSpinBox()
        self._radius_spin.setRange(0, 64)
        form.addRow("Corner radius:", self._radius_spin)

        self._badge_check = QCheckBox("Show rating badge on icon")
        form.addRow("", self._badge_check)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(128, 256)
        self._size_spin.setSingleStep(128)
        self._size_spin.setSuffix(" px")
        self._size_spin.setToolTip("Size of the largest image inside the .ico (Windows icons max out at 256 px).")
        form.addRow("Icon resolution:", self._size_spin)
        outer.addLayout(form, 1)

        side = QVBoxLayout()
        side.setSpacing(6)
        cap = QLabel("LIVE PREVIEW")
        cap.setObjectName("sectionLabel")
        side.addWidget(cap)
        self._sample = QLabel()
        self._sample.setFixedSize(_SAMPLE_SIZE + 16, _SAMPLE_SIZE + 16)
        self._sample.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sample.setStyleSheet("background: #0d0d12; border: 1px solid #25253a; border-radius: 10px;")
        side.addWidget(self._sample)
        hint = QLabel("Changes show instantly.")
        hint.setObjectName("hint")
        side.addWidget(hint)
        side.addStretch(1)
        outer.addLayout(side)

        self._load_icon_widgets(self._prefs)
        for sig in (
            self._style_combo.currentIndexChanged, self._rounded.toggled, self._radius_spin.valueChanged,
            self._badge_check.toggled, self._size_spin.valueChanged,
        ):
            sig.connect(self._update_sample)
        self._rounded.toggled.connect(lambda on: self._radius_spin.setEnabled(on))
        return w

    def _load_icon_widgets(self, prefs: dict):
        idx = next((i for i, (v, _) in enumerate(_STYLES) if v == prefs.get("icon_style")), 0)
        self._style_combo.setCurrentIndex(idx)
        self._rounded.setChecked(prefs.get("rounded_corners", True))
        self._radius_spin.setValue(prefs.get("corner_radius", 12))
        self._radius_spin.setEnabled(self._rounded.isChecked())
        self._badge_check.setChecked(prefs.get("show_rating_badge", False))
        self._size_spin.setValue(min(256, max(128, prefs.get("icon_size", 256))))

    def _update_sample(self, *_):
        prefs = {**self._prefs, **self._collect_style_prefs()}
        try:
            icon = render_icon(self._poster, ContentType.UNKNOWN, 8.4, prefs, upscale=False)
            icon = icon.resize((_SAMPLE_SIZE, _SAMPLE_SIZE), Image.LANCZOS).convert("RGBA")
            qimg = QImage(icon.tobytes("raw", "RGBA"), _SAMPLE_SIZE, _SAMPLE_SIZE, QImage.Format.Format_RGBA8888)
            self._sample.setPixmap(QPixmap.fromImage(qimg))
        except Exception:
            self._sample.setText("Preview unavailable")

    # ── Behavior tab ───────────────────────────────────────────

    def _build_behavior_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(14, 18, 14, 12)
        form.setSpacing(10)
        form.setHorizontalSpacing(14)

        self._upscale_check = QCheckBox("AI upscale low-res anime images (waifu2x)")
        self._upscale_check.setToolTip("Needs the optional waifu2x binary; otherwise a high-quality resize is used.")
        self._upscale_check.setChecked(self._prefs.get("upscale_anime", True))
        form.addRow(self._upscale_check)

        self._threshold_spin = QSpinBox()
        self._threshold_spin.setRange(50, 100)
        self._threshold_spin.setSuffix("%")
        self._threshold_spin.setValue(self._prefs.get("auto_apply_threshold", 85))
        form.addRow("Auto-apply threshold:", self._threshold_spin)

        note = QLabel(
            "After “Find Icons”, a folder whose best match is at least this confident is applied "
            "automatically. Anything lower waits as <b>Ready to apply</b> so you can review it first. "
            "Set 100% to review everything."
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.RichText)
        note.setStyleSheet(
            "color: #8a8ab8; font-size: 11px; background: #13131a;"
            " border: 1px solid #1e1e2e; border-radius: 6px; padding: 10px 12px;"
        )
        form.addRow(note)
        return w

    # ── Save / reset ───────────────────────────────────────────

    def _collect_style_prefs(self) -> dict:
        return {
            "icon_style": self._style_combo.currentData(),
            "rounded_corners": self._rounded.isChecked(),
            "corner_radius": self._radius_spin.value(),
            "show_rating_badge": self._badge_check.isChecked(),
            "icon_size": self._size_spin.value(),
        }

    def _restore_defaults(self):
        d = defaults()
        self._load_icon_widgets(d)
        self._upscale_check.setChecked(d["upscale_anime"])
        self._threshold_spin.setValue(d["auto_apply_threshold"])
        self._update_sample()

    def _save(self):
        set_api_key("tmdb", self._tmdb_key.text().strip())
        set_api_key("igdb_client_id", self._igdb_id.text().strip())
        set_api_key("igdb_client_secret", self._igdb_secret.text().strip())

        self._prefs.update(self._collect_style_prefs())
        self._prefs.update({
            "upscale_anime": self._upscale_check.isChecked(),
            "auto_apply_threshold": self._threshold_spin.value(),
        })
        # Re-read so window position / last folder written meanwhile aren't clobbered.
        latest = load_prefs()
        latest.update(self._prefs)
        for k in ("last_dir", "window_geometry"):
            latest[k] = load_prefs().get(k, "")
        save_prefs(latest)
        self.accept()
