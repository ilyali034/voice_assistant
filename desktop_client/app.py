import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("VoiceAssistant")
    app.setApplicationName("DesktopClient")
    app.setFont(QFont("Segoe UI", 10))

    window = MainWindow()
    window.show()
    return app.exec()