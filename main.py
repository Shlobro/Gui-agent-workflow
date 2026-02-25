"""Entry point for the LLM Workflow GUI."""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Register all providers
import src.llm  # noqa: F401

from src.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LLM Workflow")
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
