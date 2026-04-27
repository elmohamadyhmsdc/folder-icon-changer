import sys
import os

# Ensure the project root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Folder Icon Changer")
    app.setOrganizationName("FolderIconChanger")

    _icon_path = os.path.join(os.path.dirname(__file__), "resources", "icon.png")
    if os.path.exists(_icon_path):
        app_icon = QIcon(_icon_path)
        app.setWindowIcon(app_icon)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
