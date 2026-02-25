"""Canonical entry point for the LLM Workflow GUI."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

# Register built-in providers on startup.
import src.llm  # noqa: F401
from src.gui.main_window import MainWindow


def create_application(argv: list[str]) -> QApplication:
    """Create and configure the Qt application instance."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv)
    app.setApplicationName("LLM Workflow")
    app.setOrganizationName("GUI Workflow")
    app.setApplicationDisplayName("LLM Workflow")
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    return app


def main() -> int:
    """Start the GUI and return the process exit code."""
    app = create_application(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
