import sys
import os

# Ensure the project root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from app.ui.main_window import MainWindow
from app.utils import threads
from app.utils.admin import is_admin


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Folder Icon Changer")
    app.setOrganizationName("FolderIconChanger")

    _icon_path = os.path.join(os.path.dirname(__file__), "resources", "icon.png")
    if os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))

    # No blocking dialog at startup: the main window shows a dismissible banner
    # with a "Restart as Administrator" button when elevation is missing.
    admin = is_admin()

    window = MainWindow(is_admin=admin)
    window.show()
    code = app.exec()
    threads.wait_all(3000)
    sys.exit(code)


if __name__ == "__main__":
    main()
