import ctypes
import sys
import os

# Ensure the project root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon
from app.ui.main_window import MainWindow


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> None:
    script = os.path.abspath(sys.argv[0])
    extra = " ".join(f'"{a}"' for a in sys.argv[1:])
    params = f'"{script}"' if not extra else f'"{script}" {extra}'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Folder Icon Changer")
    app.setOrganizationName("FolderIconChanger")

    _icon_path = os.path.join(os.path.dirname(__file__), "resources", "icon.png")
    if os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))

    admin = _is_admin()
    if not admin:
        msg = QMessageBox()
        msg.setWindowTitle("Administrator Rights Recommended")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(
            "Folder Icon Changer works best with <b>Administrator</b> rights.<br><br>"
            "Without them, icon changes may silently fail on protected folders."
        )
        msg.setInformativeText("Restart as Administrator now?")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        if msg.exec() == QMessageBox.StandardButton.Yes:
            _relaunch_as_admin()
            sys.exit(0)

    window = MainWindow(is_admin=admin)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
