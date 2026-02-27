"""PropertiesPanel — animated side-panel for editing node properties."""

from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Signal,
    Qt,
)
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .llm_widget import ModelSelector, populate_model_selector

PANEL_WIDTH = 360

_PANEL_STYLE = """
    QWidget#properties_panel_root {
        background: #1e1e1e;
        border-left: 1px solid #333;
    }
    QLabel#section_label {
        color: #888888;
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 1px;
    }
    QLabel { color: #aaaaaa; font-size: 10px; }
    QLineEdit {
        background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
        padding: 4px 6px; color: #e8e8e8; font-size: 13px;
    }
    QLineEdit:focus { border: 1px solid #3a8ef5; }
    QPushButton {
        background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
        padding: 4px 8px; color: #e8e8e8; text-align: left;
    }
    QPushButton:hover { border: 1px solid #555; }
    QPushButton:pressed { background: #222222; }
    QListWidget {
        background: #2a2a2a; color: #e8e8e8;
        border: 1px solid #555555; border-radius: 4px;
        padding: 2px; outline: 0px;
    }
    QListWidget::item { padding: 4px 6px; }
    QListWidget::item:selected { background: #3a8ef5; color: #ffffff; }
    QListWidget::item:hover { background: #324056; }
    QPlainTextEdit {
        background: #1e1e1e; border: 1px solid #444; border-radius: 4px;
        padding: 4px; color: #e8e8e8; font-family: monospace; font-size: 11px;
    }
    QPlainTextEdit:focus { border: 1px solid #3a8ef5; }
    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical {
        background: #1e1e1e; width: 8px; border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #444; border-radius: 4px; min-height: 20px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""


# ---------------------------------------------------------------------------
# LLM form
# ---------------------------------------------------------------------------

class _LLMForm(QWidget):
    """Form widget for editing an LLMNode's properties."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        type_label = QLabel("LLM CALL")
        type_label.setObjectName("section_label")
        layout.addWidget(type_label)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name…")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        model_label = QLabel("Model")
        layout.addWidget(model_label)
        self.model_selector = ModelSelector(popup_parent=self)
        populate_model_selector(self.model_selector)
        layout.addWidget(self.model_selector)

        layout.addSpacing(4)

        prompt_label = QLabel("Prompt")
        layout.addWidget(prompt_label)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("Enter your prompt here…")
        self.prompt_edit.setMinimumHeight(100)
        self.prompt_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.prompt_edit, stretch=1)

        layout.addSpacing(4)

        self._output_frame = QFrame()
        self._output_frame.setVisible(False)
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(4)
        self.output_label = QLabel("Output")
        out_layout.addWidget(self.output_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(80)
        out_layout.addWidget(self.output_edit)
        layout.addWidget(self._output_frame)

    def show_output(self, visible: bool):
        self._output_frame.setVisible(visible)


# ---------------------------------------------------------------------------
# FileOp form
# ---------------------------------------------------------------------------

class _FileOpForm(QWidget):
    """Form widget for editing a FileOpNode's properties."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        self._type_label = QLabel("FILE OP")
        self._type_label.setObjectName("section_label")
        layout.addWidget(self._type_label)

        layout.addSpacing(4)

        name_label = QLabel("Name")
        layout.addWidget(name_label)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Node name…")
        layout.addWidget(self.title_edit)

        layout.addSpacing(4)

        fn_label = QLabel("Filename")
        layout.addWidget(fn_label)
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("e.g. output.txt")
        layout.addWidget(self.filename_edit)

        layout.addSpacing(4)

        self._output_frame = QFrame()
        self._output_frame.setVisible(False)
        out_layout = QVBoxLayout(self._output_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.setSpacing(4)
        self.output_label = QLabel("Result")
        out_layout.addWidget(self.output_label)
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(60)
        out_layout.addWidget(self.output_edit)
        layout.addWidget(self._output_frame)

        layout.addStretch(1)

    def set_op_type_label(self, label: str):
        self._type_label.setText(label)

    def show_output(self, visible: bool):
        self._output_frame.setVisible(visible)


# ---------------------------------------------------------------------------
# PropertiesPanel
# ---------------------------------------------------------------------------

class PropertiesPanel(QWidget):
    """Animated drawer panel that slides in from the right when a node is selected."""

    # Signals emitted when the user commits changes
    title_committed = Signal(str, str, str)     # node_id, old_title, new_title
    model_changed = Signal(str, str, str)        # node_id, old_model_id, new_model_id
    prompt_committed = Signal(str, str)          # node_id, text
    filename_committed = Signal(str, str)        # node_id, text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("properties_panel_root")
        self.setStyleSheet(_PANEL_STYLE)
        self.setMinimumWidth(0)
        self.setMaximumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._current_node: Optional[object] = None
        self._old_title: str = ""
        self._prompt_dirty: bool = False
        self._filename_dirty: bool = False
        self._is_committing: bool = False

        # Animation on maximumWidth
        self._anim = QPropertyAnimation(self, b"maximumWidth")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Stack: page 0 = empty, page 1 = LLM form, page 2 = FileOp form
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._stack = QStackedWidget()
        outer_layout.addWidget(self._stack)

        # Page 0 — empty placeholder
        self._stack.addWidget(QWidget())

        # Page 1 — LLM form (inside a scroll area)
        self._llm_form = _LLMForm()
        llm_scroll = QScrollArea()
        llm_scroll.setWidgetResizable(True)
        llm_scroll.setWidget(self._llm_form)
        llm_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(llm_scroll)

        # Page 2 — FileOp form (inside a scroll area)
        self._file_form = _FileOpForm()
        file_scroll = QScrollArea()
        file_scroll.setWidgetResizable(True)
        file_scroll.setWidget(self._file_form)
        file_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(file_scroll)

        self._wire_signals()

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self):
        # LLM form
        self._llm_form.title_edit.editingFinished.connect(self._on_llm_title_committed)
        self._llm_form.model_selector.model_changed.connect(self._on_model_changed)
        self._llm_form.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self._llm_form.prompt_edit.installEventFilter(self)

        # FileOp form
        self._file_form.title_edit.editingFinished.connect(self._on_file_title_committed)
        self._file_form.filename_edit.editingFinished.connect(self._on_filename_committed)
        self._file_form.filename_edit.textChanged.connect(self._on_filename_changed)
        self._file_form.filename_edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.FocusOut:
            if obj is self._llm_form.prompt_edit and self._prompt_dirty:
                self._flush_prompt()
            elif obj is self._file_form.filename_edit and self._filename_dirty:
                self._flush_filename()
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Slot helpers
    # ------------------------------------------------------------------

    def _on_llm_title_committed(self):
        if self._current_node is None:
            return
        new_title = self._llm_form.title_edit.text()
        if new_title != self._old_title:
            self.title_committed.emit(self._current_node.node_id, self._old_title, new_title)
            self._old_title = new_title

    def _on_file_title_committed(self):
        if self._current_node is None:
            return
        new_title = self._file_form.title_edit.text()
        if new_title != self._old_title:
            self.title_committed.emit(self._current_node.node_id, self._old_title, new_title)
            self._old_title = new_title

    def _on_model_changed(self, old_id: str, new_id: str):
        if self._current_node is None:
            return
        self.model_changed.emit(self._current_node.node_id, old_id, new_id)

    def _on_prompt_changed(self):
        self._prompt_dirty = True

    def _flush_prompt(self):
        if self._current_node is None:
            return
        text = self._llm_form.prompt_edit.toPlainText()
        self.prompt_committed.emit(self._current_node.node_id, text)
        self._prompt_dirty = False

    def _on_filename_changed(self):
        self._filename_dirty = True

    def _on_filename_committed(self):
        if self._filename_dirty:
            self._flush_filename()

    def _flush_filename(self):
        if self._current_node is None:
            return
        text = self._file_form.filename_edit.text()
        self.filename_committed.emit(self._current_node.node_id, text)
        self._filename_dirty = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def commit_pending_edits(self) -> None:
        """Commit visible-form edits in a stable order."""
        if self._is_committing:
            return

        from .llm_node import LLMNode
        from .file_op_node import FileOpNode

        self._is_committing = True
        try:
            if isinstance(self._current_node, LLMNode):
                # Flush content first, then title; title commit can trigger panel refresh.
                if self._prompt_dirty:
                    self._flush_prompt()
                self._on_llm_title_committed()
            elif isinstance(self._current_node, FileOpNode):
                # Flush content first, then title; title commit can trigger panel refresh.
                if self._filename_dirty:
                    self._flush_filename()
                self._on_file_title_committed()
        finally:
            self._is_committing = False

    def show_for_node(self, node) -> None:
        """Load node data into the form, switch page, and animate open."""
        from .llm_node import LLMNode
        from .file_op_node import FileOpNode

        # Commit any pending edits for the previous node before switching.
        if self._current_node is not None and self._current_node is not node:
            self.commit_pending_edits()

        self._current_node = node

        if isinstance(node, LLMNode):
            self._load_llm_form(node)
            self._stack.setCurrentIndex(1)
        elif isinstance(node, FileOpNode):
            self._load_file_form(node)
            self._stack.setCurrentIndex(2)
        else:
            self._stack.setCurrentIndex(0)

        self._animate_to(PANEL_WIDTH)

    def hide_panel(self) -> None:
        """Flush pending edits, then animate the panel shut."""
        self.commit_pending_edits()
        self._current_node = None
        self._animate_to(0)

    def maybe_append_output(self, node, line: str) -> None:
        """Append a line to the output area if `node` is currently displayed."""
        if node is not self._current_node:
            return
        from .llm_node import LLMNode
        from .file_op_node import FileOpNode
        if isinstance(node, LLMNode):
            self._llm_form.show_output(True)
            self._llm_form.output_edit.appendPlainText(line)
        elif isinstance(node, FileOpNode):
            self._file_form.show_output(True)
            self._file_form.output_edit.appendPlainText(line)

    def maybe_clear_output(self, node) -> None:
        """Clear the output area if `node` is currently displayed."""
        if node is not self._current_node:
            return
        from .llm_node import LLMNode
        from .file_op_node import FileOpNode
        if isinstance(node, LLMNode):
            self._llm_form.output_edit.clear()
            self._llm_form.show_output(False)
        elif isinstance(node, FileOpNode):
            self._file_form.output_edit.clear()
            self._file_form.show_output(False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_llm_form(self, node) -> None:
        form = self._llm_form
        form.title_edit.blockSignals(True)
        form.model_selector.blockSignals(True)
        form.prompt_edit.blockSignals(True)

        form.title_edit.setText(node.title)
        form.model_selector.set_model_id(node.model_id)
        form.prompt_edit.setPlainText(node.prompt_text)

        # Output area
        if node.output_text:
            form.show_output(True)
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
        else:
            form.output_edit.clear()
            form.show_output(False)

        form.title_edit.blockSignals(False)
        form.model_selector.blockSignals(False)
        form.prompt_edit.blockSignals(False)

        self._old_title = node.title
        self._prompt_dirty = False

    def _load_file_form(self, node) -> None:
        from .file_op_node import NODE_TYPE_DISPLAY_NAMES
        form = self._file_form
        form.title_edit.blockSignals(True)
        form.filename_edit.blockSignals(True)

        form.set_op_type_label(
            NODE_TYPE_DISPLAY_NAMES.get(node.node_type, "FILE OP").upper()
        )
        form.title_edit.setText(node.title)
        form.filename_edit.setText(node.filename)

        if node.output_text:
            form.show_output(True)
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
        else:
            form.output_edit.clear()
            form.show_output(False)

        form.title_edit.blockSignals(False)
        form.filename_edit.blockSignals(False)

        self._old_title = node.title
        self._filename_dirty = False

    def _animate_to(self, target_width: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(target_width)
        self._anim.start()

    # ------------------------------------------------------------------
    # Called by MainWindow after undo/redo changes node data
    # ------------------------------------------------------------------

    def refresh_if_current(self, node) -> None:
        """Reload form fields if this node is currently shown."""
        if node is not self._current_node:
            return
        self.show_for_node(node)
