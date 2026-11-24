"""Central dark theme for the whole app (one place to tweak colours)."""

# ── Palette ───────────────────────────────────────────────────────────
BG = "#0d0d12"
SURFACE = "#13131a"
SURFACE_2 = "#1a1a26"
SURFACE_3 = "#222233"
BORDER = "#25253a"
BORDER_STRONG = "#34344f"
TEXT = "#e4e4f2"
TEXT_DIM = "#9a9ac0"
TEXT_MUTED = "#6a6a92"
ACCENT = "#6366f1"
ACCENT_HOVER = "#7578f5"
ACCENT_DEEP = "#4f52cc"
SUCCESS = "#4ade80"
WARNING = "#fbbf24"
DANGER = "#f87171"
INFO = "#60a5fa"

DARK_STYLE = f"""
QMainWindow, QDialog, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI";
    font-size: 13px;
}}
QWidget:disabled {{ color: #4a4a6a; }}

QToolTip {{
    background: {SURFACE_3};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    padding: 5px 8px;
    border-radius: 4px;
}}

/* ── Toolbar ──────────────────────────────────────────────── */
QFrame#toolbarFrame {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}

/* ── Buttons ──────────────────────────────────────────────── */
QPushButton {{
    background: {SURFACE_2};
    color: #cfcfee;
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 28px;
}}
QPushButton:hover {{ background: {SURFACE_3}; border-color: #46466a; color: {TEXT}; }}
QPushButton:pressed {{ background: #15151f; border-color: {ACCENT}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #46466a; border-color: #1e1e2e; background: #12121a; }}

QPushButton#primaryBtn {{
    background: {ACCENT_DEEP};
    color: #ffffff;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#primaryBtn:hover {{ background: {ACCENT}; border-color: #818cf8; }}
QPushButton#primaryBtn:pressed {{ background: #3b3eaa; }}
QPushButton#primaryBtn:disabled {{ background: #232338; border-color: #232338; color: #5a5a80; }}

QPushButton#dangerBtn {{
    background: #2e1010;
    color: {DANGER};
    border: 1px solid #6b1c1c;
}}
QPushButton#dangerBtn:hover {{ background: #4a1717; border-color: #ef4444; color: #fca5a5; }}
QPushButton#dangerBtn:disabled {{ background: #17100f; color: #5a3a3a; border-color: #2a1a1a; }}

QPushButton#ghostBtn {{
    background: transparent;
    border: 1px solid transparent;
    color: {TEXT_DIM};
}}
QPushButton#ghostBtn:hover {{ background: {SURFACE_2}; color: {TEXT}; }}

QPushButton#iconBtn {{ padding: 5px 0px; min-width: 34px; max-width: 34px; }}
QPushButton#iconBtn::menu-indicator {{ image: none; width: 0; }}

QPushButton#bigBtn {{
    padding: 10px 20px;
    min-height: 34px;
    font-size: 13px;
}}

/* ── Table ────────────────────────────────────────────────── */
QTableWidget {{
    background: {BG};
    alternate-background-color: #0f0f16;
    gridline-color: transparent;
    color: #d6d6ee;
    border: 1px solid {BORDER};
    border-radius: 8px;
    outline: none;
}}
QTableWidget::item {{ padding: 4px 8px; border: none; }}
QTableWidget::item:selected {{ background: #232352; color: {TEXT}; }}
QTableWidget::item:hover {{ background: #151528; }}
QHeaderView::section {{
    background: {SURFACE};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 7px 8px;
    font-size: 11px;
    font-weight: bold;
}}
QHeaderView {{ background: {SURFACE}; }}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

/* ── Panels / cards ───────────────────────────────────────── */
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#sectionLabel {{
    color: {TEXT_MUTED};
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#hint {{ color: {TEXT_MUTED}; font-size: 11px; background: transparent; }}
QLabel#h1 {{ color: {TEXT}; font-size: 20px; font-weight: 600; background: transparent; }}
QLabel#h2 {{ color: {TEXT}; font-size: 14px; font-weight: 600; background: transparent; }}
QLabel#errorBox {{
    background: #200e0e;
    color: #fca5a5;
    border: 1px solid #5c1a1a;
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 11px;
}}

/* ── Banners ──────────────────────────────────────────────── */
QFrame#bannerWarn {{ background: #2e2200; border-bottom: 1px solid #6b4d00; }}
QFrame#bannerInfo {{ background: #12102a; border-bottom: 1px solid #3b3380; }}
QFrame#bannerWarn QLabel, QFrame#bannerInfo QLabel {{ background: transparent; }}

/* ── Input fields ─────────────────────────────────────────── */
QLineEdit, QSpinBox {{
    background: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 26px;
    selection-background-color: {ACCENT_DEEP};
}}
QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; background: #1d1d2d; }}
QLineEdit:disabled, QSpinBox:disabled {{ color: #4a4a6a; background: #12121a; }}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {SURFACE_3}; border: none; width: 18px; border-radius: 2px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: #3a3a58; }}

QComboBox {{
    background: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 26px;
}}
QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: #2e2e4a;
    outline: none;
    padding: 2px;
}}

QCheckBox {{ spacing: 8px; color: #cfcfee; background: transparent; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #46466a; background: {SURFACE_2};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}

/* ── Tabs ─────────────────────────────────────────────────── */
QTabWidget::pane {{ border: 1px solid {BORDER}; background: {BG}; top: -1px; border-radius: 6px; }}
QTabBar::tab {{
    background: {SURFACE};
    color: #7c7cac;
    border: 1px solid {BORDER};
    border-bottom: none;
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{ background: {BG}; color: {TEXT}; border-bottom: 1px solid {BG}; }}
QTabBar::tab:hover:!selected {{ background: {SURFACE_2}; color: #b0b0d8; }}

/* ── Lists ────────────────────────────────────────────────── */
QListWidget {{
    background: {BG};
    color: #d6d6ee;
    border: 1px solid {BORDER};
    border-radius: 8px;
    outline: none;
}}
QListWidget::item {{ padding: 2px 10px; border-bottom: 1px solid #14141f; }}
QListWidget::item:selected {{ background: #232352; color: {TEXT}; }}
QListWidget::item:hover:!selected {{ background: #151528; }}

/* ── Menus ────────────────────────────────────────────────── */
QMenu {{
    background: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 5px;
}}
QMenu::item {{ padding: 7px 26px 7px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: #2a2a58; }}
QMenu::item:disabled {{ color: #4a4a6a; }}
QMenu::separator {{ height: 1px; background: {BORDER_STRONG}; margin: 5px 8px; }}

/* ── Scrollbars ───────────────────────────────────────────── */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2e2e45; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #5a5a90; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #2e2e45; border-radius: 5px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: #5a5a90; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Splitter ─────────────────────────────────────────────── */
QSplitter::handle {{ background: transparent; }}

/* ── Status bar / progress ────────────────────────────────── */
QStatusBar {{
    background: #0a0a10;
    color: #7a7aa6;
    border-top: 1px solid #1a1a28;
    font-size: 12px;
}}
QStatusBar::item {{ border: none; }}
QProgressBar {{
    background: {SURFACE_2};
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #b0b0d0;
    font-size: 11px;
    min-height: 14px;
    max-height: 14px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

QDialogButtonBox QPushButton {{ min-width: 84px; }}

QGroupBox {{
    color: #7c7cac;
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    font-size: 11px;
    font-weight: bold;
}}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; left: 10px; }}

QLabel {{ color: #cfcfee; background: transparent; }}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT}; }}
"""
