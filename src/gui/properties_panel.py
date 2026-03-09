"""PropertiesPanel - animated side-panel for editing node properties."""

from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Signal,
    Qt,
)
from PySide6.QtWidgets import (
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ._panel_forms import (
    _LLMForm,
    _FileOpForm,
    _ConditionalForm,
    _LoopForm,
    _GitActionForm,
    _AttentionForm,
)

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
    QComboBox {
        background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
        padding: 4px 6px; color: #e8e8e8; font-size: 13px;
    }
    QComboBox:focus { border: 1px solid #3a8ef5; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView {
        background: #2a2a2a; color: #e8e8e8;
        border: 1px solid #555; selection-background-color: #3a8ef5;
    }
    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical {
        background: #1e1e1e; width: 8px; border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #444; border-radius: 4px; min-height: 20px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""


class PropertiesPanel(QWidget):
    """Animated drawer panel that slides in from the right when a node is selected."""

    title_committed = Signal(str, str, str)
    model_changed = Signal(str, str, str)
    prompt_committed = Signal(str, str)
    filename_committed = Signal(str, str)
    attention_message_committed = Signal(str, str)
    op_type_changed = Signal(str, str, str)
    condition_type_changed = Signal(str, str, str)
    loop_count_changed = Signal(str, int, int)
    git_action_changed = Signal(str, str, str)

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
        self._cond_filename_dirty: bool = False
        self._attention_message_dirty: bool = False
        self._git_commit_msg_dirty: bool = False
        self._git_commit_msg_file_dirty: bool = False
        self._is_committing: bool = False

        self._anim = QPropertyAnimation(self, b"maximumWidth")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._stack = QStackedWidget()
        outer_layout.addWidget(self._stack)

        self._stack.addWidget(QWidget())

        self._llm_form = _LLMForm()
        llm_scroll = QScrollArea()
        llm_scroll.setWidgetResizable(True)
        llm_scroll.setWidget(self._llm_form)
        llm_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(llm_scroll)

        self._file_form = _FileOpForm()
        file_scroll = QScrollArea()
        file_scroll.setWidgetResizable(True)
        file_scroll.setWidget(self._file_form)
        file_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(file_scroll)

        self._cond_form = _ConditionalForm()
        cond_scroll = QScrollArea()
        cond_scroll.setWidgetResizable(True)
        cond_scroll.setWidget(self._cond_form)
        cond_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(cond_scroll)

        self._loop_form = _LoopForm()
        loop_scroll = QScrollArea()
        loop_scroll.setWidgetResizable(True)
        loop_scroll.setWidget(self._loop_form)
        loop_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(loop_scroll)

        self._git_form = _GitActionForm()
        git_scroll = QScrollArea()
        git_scroll.setWidgetResizable(True)
        git_scroll.setWidget(self._git_form)
        git_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(git_scroll)

        self._attention_form = _AttentionForm()
        attention_scroll = QScrollArea()
        attention_scroll.setWidgetResizable(True)
        attention_scroll.setWidget(self._attention_form)
        attention_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(attention_scroll)

        self._wire_signals()

    def _wire_signals(self):
        self._llm_form.title_edit.editingFinished.connect(self._on_llm_title_committed)
        self._llm_form.model_selector.model_changed.connect(self._on_model_changed)
        self._llm_form.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self._llm_form.prompt_edit.installEventFilter(self)

        self._file_form.title_edit.editingFinished.connect(self._on_file_title_committed)
        self._file_form.filename_edit.editingFinished.connect(self._on_filename_committed)
        self._file_form.filename_edit.textChanged.connect(self._on_filename_changed)
        self._file_form.filename_edit.installEventFilter(self)
        self._file_form.op_type_changed.connect(self._on_op_type_changed)

        self._cond_form.title_edit.editingFinished.connect(self._on_cond_title_committed)
        self._cond_form.filename_edit.editingFinished.connect(self._on_cond_filename_committed)
        self._cond_form.filename_edit.textChanged.connect(self._on_cond_filename_changed)
        self._cond_form.filename_edit.installEventFilter(self)
        self._cond_form.condition_type_changed.connect(self._on_condition_type_changed)

        self._loop_form.title_edit.editingFinished.connect(self._on_loop_title_committed)
        self._loop_form.loop_count_changed.connect(self._on_loop_count_changed)

        self._git_form.title_edit.editingFinished.connect(self._on_git_title_committed)
        self._git_form.git_action_changed.connect(self._on_git_action_changed)
        self._git_form.msg_source_changed.connect(self._on_git_msg_source_changed)
        self._git_form.commit_msg_edit.textChanged.connect(self._on_git_commit_msg_changed)
        self._git_form.commit_msg_edit.editingFinished.connect(self._on_git_commit_msg_committed)
        self._git_form.commit_msg_edit.installEventFilter(self)
        self._git_form.commit_msg_file_edit.textChanged.connect(self._on_git_commit_msg_file_changed)
        self._git_form.commit_msg_file_edit.editingFinished.connect(self._on_git_commit_msg_file_committed)
        self._git_form.commit_msg_file_edit.installEventFilter(self)

        self._attention_form.title_edit.editingFinished.connect(self._on_attention_title_committed)
        self._attention_form.message_edit.textChanged.connect(self._on_attention_message_changed)
        self._attention_form.message_edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.FocusOut:
            if obj is self._llm_form.prompt_edit and self._prompt_dirty:
                self._flush_prompt()
            elif obj is self._file_form.filename_edit and self._filename_dirty:
                self._flush_filename()
            elif obj is self._cond_form.filename_edit and self._cond_filename_dirty:
                self._flush_cond_filename()
            elif obj is self._attention_form.message_edit and self._attention_message_dirty:
                self._flush_attention_message()
            elif obj is self._git_form.commit_msg_edit and self._git_commit_msg_dirty:
                self._flush_git_commit_msg()
            elif obj is self._git_form.commit_msg_file_edit and self._git_commit_msg_file_dirty:
                self._flush_git_commit_msg_file()
        return super().eventFilter(obj, event)

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

    def _on_op_type_changed(self, old_type: str, new_type: str):
        if self._current_node is None:
            return
        self.op_type_changed.emit(self._current_node.node_id, old_type, new_type)

    def _on_cond_title_committed(self):
        if self._current_node is None:
            return
        new_title = self._cond_form.title_edit.text()
        if new_title != self._old_title:
            self.title_committed.emit(self._current_node.node_id, self._old_title, new_title)
            self._old_title = new_title

    def _on_cond_filename_changed(self):
        self._cond_filename_dirty = True

    def _on_cond_filename_committed(self):
        if self._cond_filename_dirty:
            self._flush_cond_filename()

    def _flush_cond_filename(self):
        if self._current_node is None:
            return
        text = self._cond_form.filename_edit.text()
        self.filename_committed.emit(self._current_node.node_id, text)
        self._cond_filename_dirty = False

    def _on_condition_type_changed(self, old_type: str, new_type: str):
        if self._current_node is None:
            return
        self.condition_type_changed.emit(self._current_node.node_id, old_type, new_type)

    def _on_loop_title_committed(self):
        if self._current_node is None:
            return
        new_title = self._loop_form.title_edit.text()
        if new_title != self._old_title:
            self.title_committed.emit(self._current_node.node_id, self._old_title, new_title)
            self._old_title = new_title

    def _on_loop_count_changed(self, old_count: int, new_count: int):
        if self._current_node is None:
            return
        self.loop_count_changed.emit(self._current_node.node_id, old_count, new_count)

    def _on_git_title_committed(self):
        if self._current_node is None:
            return
        new_title = self._git_form.title_edit.text()
        if new_title != self._old_title:
            self.title_committed.emit(self._current_node.node_id, self._old_title, new_title)
            self._old_title = new_title

    def _on_git_action_changed(self, old_action: str, new_action: str):
        if self._current_node is None:
            return
        self.git_action_changed.emit(self._current_node.node_id, old_action, new_action)

    def _on_git_msg_source_changed(self, _old_source: str, new_source: str):
        if self._current_node is None:
            return
        self._current_node.msg_source = new_source

    def _on_git_commit_msg_changed(self):
        self._git_commit_msg_dirty = True

    def _on_git_commit_msg_committed(self):
        if self._git_commit_msg_dirty:
            self._flush_git_commit_msg()

    def _flush_git_commit_msg(self):
        if self._current_node is None:
            return
        self._current_node.commit_msg = self._git_form.commit_msg_edit.text()
        self._git_commit_msg_dirty = False

    def _on_git_commit_msg_file_changed(self):
        self._git_commit_msg_file_dirty = True

    def _on_git_commit_msg_file_committed(self):
        if self._git_commit_msg_file_dirty:
            self._flush_git_commit_msg_file()

    def _flush_git_commit_msg_file(self):
        if self._current_node is None:
            return
        self._current_node.commit_msg_file = self._git_form.commit_msg_file_edit.text()
        self._git_commit_msg_file_dirty = False

    def _on_attention_title_committed(self):
        if self._current_node is None:
            return
        new_title = self._attention_form.title_edit.text()
        if new_title != self._old_title:
            self.title_committed.emit(self._current_node.node_id, self._old_title, new_title)
            self._old_title = new_title

    def _on_attention_message_changed(self):
        self._attention_message_dirty = True

    def _flush_attention_message(self):
        if self._current_node is None:
            return
        text = self._attention_form.message_edit.toPlainText()
        self.attention_message_committed.emit(self._current_node.node_id, text)
        self._attention_message_dirty = False

    def commit_pending_edits(self) -> None:
        """Commit visible-form edits in a stable order."""
        if self._is_committing:
            return

        from .llm_node import LLMNode
        from .file_op_node import AttentionNode, FileOpNode
        from .conditional_node import ConditionalNode
        from .loop_node import LoopNode
        from .git_action_node import GitActionNode

        self._is_committing = True
        try:
            if isinstance(self._current_node, LLMNode):
                if self._prompt_dirty:
                    self._flush_prompt()
                self._on_llm_title_committed()
            elif isinstance(self._current_node, AttentionNode):
                if self._attention_message_dirty:
                    self._flush_attention_message()
                self._on_attention_title_committed()
            elif isinstance(self._current_node, FileOpNode):
                if self._filename_dirty:
                    self._flush_filename()
                self._on_file_title_committed()
            elif isinstance(self._current_node, ConditionalNode):
                if self._cond_filename_dirty:
                    self._flush_cond_filename()
                self._on_cond_title_committed()
            elif isinstance(self._current_node, LoopNode):
                self._on_loop_title_committed()
            elif isinstance(self._current_node, GitActionNode):
                if self._git_commit_msg_dirty:
                    self._flush_git_commit_msg()
                if self._git_commit_msg_file_dirty:
                    self._flush_git_commit_msg_file()
                self._on_git_title_committed()
        finally:
            self._is_committing = False

    def show_for_node(self, node) -> None:
        """Load node data into the form, switch page, and animate open."""
        from .llm_node import LLMNode
        from .file_op_node import AttentionNode, FileOpNode
        from .conditional_node import ConditionalNode
        from .loop_node import LoopNode
        from .git_action_node import GitActionNode

        if self._current_node is not None and self._current_node is not node:
            self.commit_pending_edits()

        self._current_node = node

        if isinstance(node, LLMNode):
            self._load_llm_form(node)
            self._stack.setCurrentIndex(1)
        elif isinstance(node, ConditionalNode):
            self._load_cond_form(node)
            self._stack.setCurrentIndex(3)
        elif isinstance(node, AttentionNode):
            self._load_attention_form(node)
            self._stack.setCurrentIndex(6)
        elif isinstance(node, LoopNode):
            self._load_loop_form(node)
            self._stack.setCurrentIndex(4)
        elif isinstance(node, GitActionNode):
            self._load_git_form(node)
            self._stack.setCurrentIndex(5)
        elif isinstance(node, FileOpNode):
            self._load_file_form(node)
            self._stack.setCurrentIndex(2)
        else:
            self._stack.setCurrentIndex(0)

        self._animate_to(PANEL_WIDTH)

    def hide_panel(self) -> None:
        self.commit_pending_edits()
        self._current_node = None
        self._animate_to(0)

    def maybe_append_output(self, node, line: str) -> None:
        if node is not self._current_node:
            return
        from .llm_node import LLMNode
        from .file_op_node import AttentionNode, FileOpNode
        from .conditional_node import ConditionalNode
        from .loop_node import LoopNode
        from .git_action_node import GitActionNode
        if isinstance(node, LLMNode):
            self._llm_form.show_output(True)
            self._llm_form.output_edit.appendPlainText(line)
        elif isinstance(node, ConditionalNode):
            self._cond_form.show_output(True)
            self._cond_form.output_edit.appendPlainText(line)
        elif isinstance(node, AttentionNode):
            self._attention_form.show_output(True)
            self._attention_form.output_edit.appendPlainText(line)
        elif isinstance(node, LoopNode):
            self._loop_form.show_output(True)
            self._loop_form.output_edit.appendPlainText(line)
        elif isinstance(node, GitActionNode):
            self._git_form.show_output(True)
            self._git_form.output_edit.appendPlainText(line)
        elif isinstance(node, FileOpNode):
            self._file_form.show_output(True)
            self._file_form.output_edit.appendPlainText(line)

    def maybe_clear_output(self, node) -> None:
        if node is not self._current_node:
            return
        from .llm_node import LLMNode
        from .file_op_node import AttentionNode, FileOpNode
        from .conditional_node import ConditionalNode
        from .loop_node import LoopNode
        from .git_action_node import GitActionNode
        if isinstance(node, LLMNode):
            self._llm_form.output_edit.clear()
            self._llm_form.show_output(False)
        elif isinstance(node, ConditionalNode):
            self._cond_form.output_edit.clear()
            self._cond_form.show_output(False)
        elif isinstance(node, AttentionNode):
            self._attention_form.output_edit.clear()
            self._attention_form.show_output(False)
        elif isinstance(node, LoopNode):
            self._loop_form.output_edit.clear()
            self._loop_form.show_output(False)
        elif isinstance(node, GitActionNode):
            self._git_form.output_edit.clear()
            self._git_form.show_output(False)
        elif isinstance(node, FileOpNode):
            self._file_form.output_edit.clear()
            self._file_form.show_output(False)

    def _load_llm_form(self, node) -> None:
        form = self._llm_form
        form.title_edit.blockSignals(True)
        form.model_selector.blockSignals(True)
        form.prompt_edit.blockSignals(True)

        form.title_edit.setText(node.title)
        form.model_selector.set_model_id(node.model_id)
        form.prompt_edit.setPlainText(node.prompt_text)

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
        form = self._file_form
        form.title_edit.blockSignals(True)
        form.filename_edit.blockSignals(True)

        form.set_op_type(node.node_type)
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

    def _load_loop_form(self, node) -> None:
        form = self._loop_form
        form.title_edit.blockSignals(True)

        form.title_edit.setText(node.title)
        form.set_loop_count(node.loop_count)

        if node.output_text:
            form.show_output(True)
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
        else:
            form.output_edit.clear()
            form.show_output(False)

        form.title_edit.blockSignals(False)

        self._old_title = node.title

    def _load_cond_form(self, node) -> None:
        form = self._cond_form
        form.title_edit.blockSignals(True)
        form.filename_edit.blockSignals(True)

        form.set_condition_type(node.condition_type)
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
        self._cond_filename_dirty = False

    def _load_git_form(self, node) -> None:
        form = self._git_form
        form.title_edit.blockSignals(True)
        form.action_combo.blockSignals(True)
        form.msg_source_combo.blockSignals(True)
        form.commit_msg_edit.blockSignals(True)
        form.commit_msg_file_edit.blockSignals(True)

        form.set_git_action(node.git_action)
        form.title_edit.setText(node.title)
        form.set_msg_source(node.msg_source)
        form.commit_msg_edit.setText(node.commit_msg)
        form.commit_msg_file_edit.setText(node.commit_msg_file)

        if node.output_text:
            form.show_output(True)
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
        else:
            form.output_edit.clear()
            form.show_output(False)

        form.title_edit.blockSignals(False)
        form.action_combo.blockSignals(False)
        form.msg_source_combo.blockSignals(False)
        form.commit_msg_edit.blockSignals(False)
        form.commit_msg_file_edit.blockSignals(False)

        self._old_title = node.title
        self._git_commit_msg_dirty = False
        self._git_commit_msg_file_dirty = False

    def _load_attention_form(self, node) -> None:
        form = self._attention_form
        form.title_edit.blockSignals(True)
        form.message_edit.blockSignals(True)

        form.title_edit.setText(node.title)
        form.message_edit.setPlainText(node.message_text)

        if node.output_text:
            form.show_output(True)
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
        else:
            form.output_edit.clear()
            form.show_output(False)

        form.title_edit.blockSignals(False)
        form.message_edit.blockSignals(False)

        self._old_title = node.title
        self._attention_message_dirty = False

    def _animate_to(self, target_width: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(target_width)
        self._anim.start()

    def refresh_if_current(self, node) -> None:
        """Reload form fields if this node is currently shown."""
        if node is not self._current_node:
            return
        self.show_for_node(node)
