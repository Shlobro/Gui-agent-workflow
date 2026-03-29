"""Startup dialog for choosing the project folder to work in."""

import json
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QDialogButtonBox,
    QFrame,
)

_RECENT_FILE = Path(__file__).parent.parent.parent / ".recent_folders.json"
_MAX_RECENT = 10


def _load_recent() -> list[str]:
    try:
        with open(_RECENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [p for p in data if os.path.isdir(p)]
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def _save_recent(folders: list[str]) -> None:
    try:
        with open(_RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(folders[:_MAX_RECENT], f, indent=2)
    except OSError:
        pass


def add_to_recent(folder: str) -> None:
    """Call this whenever a folder is opened to persist it in recents."""
    recent = _load_recent()
    folder = str(Path(folder).resolve())
    if folder in recent:
        recent.remove(folder)
    recent.insert(0, folder)
    _save_recent(recent[:_MAX_RECENT])


class ProjectChooserDialog(QDialog):
    """Modal dialog shown at startup to select the working project folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Project Folder")
        self.setMinimumSize(560, 380)
        self.setModal(True)
        self._chosen: str | None = None
        self._build_ui()
        self._apply_style()

    # ------------------------------------------------------------------
    # UI construction

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(18, 18, 18, 18)

        heading = QLabel("Select the project folder to work in")
        heading.setStyleSheet("font-size: 14px; font-weight: bold; color: #e8e8e8;")
        root.addWidget(heading)

        sub = QLabel(
            "LLM calls will run with this folder as their working directory."
        )
        sub.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        root.addWidget(sub)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #333;")
        root.addWidget(line)

        # Recent folders list
        recent_label = QLabel("Recent folders:")
        recent_label.setStyleSheet("color: #cccccc;")
        root.addWidget(recent_label)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(self._accept_selected)
        root.addWidget(self._list, stretch=1)

        self._populate_recent()

        # Browse row
        browse_row = QHBoxLayout()
        browse_btn = QPushButton("Browse for Folder…")
        browse_btn.clicked.connect(self._browse)
        browse_row.addWidget(browse_btn)
        browse_row.addStretch()
        root.addLayout(browse_row)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Open")
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _populate_recent(self):
        self._list.clear()
        recent = _load_recent()
        for path in recent:
            item = QListWidgetItem(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog, QWidget { background: #1a1a1a; color: #e8e8e8; }
            QListWidget {
                background: #252525; border: 1px solid #333; border-radius: 4px;
                alternate-background-color: #2a2a2a;
            }
            QListWidget::item:selected { background: #1e4d7a; color: #ffffff; }
            QListWidget::item:hover { background: #333333; }
            QPushButton {
                background: #333; color: #e8e8e8; border: 1px solid #444;
                border-radius: 4px; padding: 5px 14px;
            }
            QPushButton:hover { background: #444; }
            QPushButton:pressed { background: #222; }
            QDialogButtonBox QPushButton { padding: 5px 18px; }
            QFrame[frameShape="4"] { color: #333; }
            QScrollBar:vertical {
                background: #20242b;
                width: 18px;
                padding: 2px;
                border-radius: 9px;
            }
            QScrollBar::handle:vertical {
                background: #6f8fb3;
                border: 2px solid #20242b;
                border-radius: 7px;
                min-height: 52px;
            }
            QScrollBar::handle:vertical:hover { background: #83a4ca; }
            QScrollBar::handle:vertical:pressed { background: #95b8df; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                background: transparent;
                width: 0px;
                height: 0px;
            }
        """)

    # ------------------------------------------------------------------
    # Slots

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose Project Folder", "",
            QFileDialog.Option.ShowDirsOnly
            | QFileDialog.Option.DontResolveSymlinks,
        )
        if folder:
            self._chosen = folder
            self.accept()

    def _accept_selected(self, *_):
        item = self._list.currentItem()
        if item:
            self._chosen = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    # ------------------------------------------------------------------
    # Public API

    @property
    def chosen_folder(self) -> str | None:
        return self._chosen
