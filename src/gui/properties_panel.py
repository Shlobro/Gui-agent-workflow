"""PropertiesPanel - resizable side panel for editing node properties."""

from typing import Optional, Sequence

from PySide6.QtCore import QEvent, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.llm.prompt_injection import compose_prompt
from ._panel_forms import (
    _AttentionForm,
    _ConditionalForm,
    _FileOpForm,
    _GitActionForm,
    _JoinForm,
    _LLMForm,
    _LoopForm,
    _ScriptForm,
)

DEFAULT_PANEL_WIDTH = 420
MIN_PANEL_WIDTH = 300
MAX_PANEL_WIDTH = 720
DEFAULT_TEXT_ZOOM = 1
MIN_TEXT_ZOOM = -3
MAX_TEXT_ZOOM = 8

_PANEL_STYLE = """
    QWidget#properties_panel_root {
        background: #1e1e1e;
        border-left: 1px solid #333;
    }
    QLabel#section_label {
        color: #888888;
        font-weight: bold;
        letter-spacing: 1px;
    }
    QLabel { color: #aaaaaa; }
    QLineEdit {
        background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
        padding: 4px 6px; color: #e8e8e8;
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
        padding: 4px; color: #e8e8e8; font-family: Consolas, "Courier New", monospace;
    }
    QPlainTextEdit:focus { border: 1px solid #3a8ef5; }
    QComboBox {
        background: #2a2a2a; border: 1px solid #444; border-radius: 4px;
        padding: 4px 6px; color: #e8e8e8;
    }
    QComboBox:focus { border: 1px solid #3a8ef5; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView {
        background: #2a2a2a; color: #e8e8e8;
        border: 1px solid #555; selection-background-color: #3a8ef5;
    }
    QScrollArea { background: transparent; border: none; }
    QTabWidget::pane {
        border: 1px solid #3b3b3b;
        border-radius: 4px;
        top: -1px;
    }
    QTabBar::tab {
        background: #2a2a2a;
        border: 1px solid #3b3b3b;
        border-bottom: none;
        padding: 5px 12px;
        margin-right: 2px;
        color: #bbbbbb;
    }
    QTabBar::tab:selected {
        background: #1f2833;
        color: #f0f0f0;
    }
    QTabBar::tab:hover:!selected {
        background: #323943;
    }
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
    QScrollBar:horizontal {
        background: #20242b;
        height: 18px;
        padding: 2px;
        border-radius: 9px;
    }
    QScrollBar::handle:horizontal {
        background: #6f8fb3;
        border: 2px solid #20242b;
        border-radius: 7px;
        min-width: 52px;
    }
    QScrollBar::handle:horizontal:hover { background: #83a4ca; }
    QScrollBar::handle:horizontal:pressed { background: #95b8df; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
    QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
    QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {
        background: transparent;
        width: 0px;
        height: 0px;
    }
"""


class _OverviewForm(QWidget):
    """Read-only panel shown when no workflow node is selected."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)

        section = QLabel("WORKFLOW OVERVIEW")
        section.setObjectName("section_label")
        layout.addWidget(section)

        self.summary_edit = QPlainTextEdit()
        self.summary_edit.setReadOnly(True)
        self.summary_edit.setPlaceholderText("No workflow information yet.")
        self.summary_edit.setMinimumHeight(220)
        self.summary_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.summary_edit, stretch=1)


class PropertiesPanel(QWidget):
    """Resizable panel that edits the currently selected node."""

    title_committed = Signal(str, str, str)
    model_changed = Signal(str, str, str)
    prompt_committed = Signal(str, str)
    filename_committed = Signal(str, str)
    attention_message_committed = Signal(str, str)
    op_type_changed = Signal(str, str, str)
    condition_type_changed = Signal(str, str, str)
    loop_count_changed = Signal(str, int, int)
    join_count_changed = Signal(str, int, int)
    git_action_changed = Signal(str, str, str)
    git_details_changed = Signal(str)
    script_path_committed = Signal(str, str)
    script_browse_requested = Signal(str)
    script_auto_send_enter_changed = Signal(str, bool)
    text_zoom_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("properties_panel_root")
        self.setStyleSheet(_PANEL_STYLE)
        self.setMinimumWidth(MIN_PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._current_node: Optional[object] = None
        self._old_title: str = ""
        self._prompt_dirty: bool = False
        self._filename_dirty: bool = False
        self._cond_filename_dirty: bool = False
        self._attention_message_dirty: bool = False
        self._git_commit_msg_dirty: bool = False
        self._git_commit_msg_file_dirty: bool = False
        self._script_path_dirty: bool = False
        self._is_committing: bool = False
        self._preferred_width: int = DEFAULT_PANEL_WIDTH
        self._text_zoom: int = DEFAULT_TEXT_ZOOM
        self._preview_prepend_templates: list[str] = []
        self._preview_append_templates: list[str] = []
        self._preview_one_off_text: str = ""
        self._preview_one_off_placement: str = "append"

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._stack = QStackedWidget()
        outer_layout.addWidget(self._stack)

        self._overview_form = _OverviewForm()
        self._stack.addWidget(self._wrap_form(self._overview_form))

        self._llm_form = _LLMForm()
        self._stack.addWidget(self._wrap_form(self._llm_form))

        self._file_form = _FileOpForm()
        self._stack.addWidget(self._wrap_form(self._file_form))

        self._cond_form = _ConditionalForm()
        self._stack.addWidget(self._wrap_form(self._cond_form))

        self._loop_form = _LoopForm()
        self._stack.addWidget(self._wrap_form(self._loop_form))

        self._join_form = _JoinForm()
        self._stack.addWidget(self._wrap_form(self._join_form))

        self._git_form = _GitActionForm()
        self._stack.addWidget(self._wrap_form(self._git_form))

        self._attention_form = _AttentionForm()
        self._stack.addWidget(self._wrap_form(self._attention_form))

        self._script_form = _ScriptForm()
        self._stack.addWidget(self._wrap_form(self._script_form))

        self._wire_signals()
        self._install_zoom_filters()
        self._apply_text_zoom()

    def _wrap_form(self, form: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

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

        self._join_form.title_edit.editingFinished.connect(self._on_join_title_committed)
        self._join_form.wait_for_count_changed.connect(self._on_join_count_changed)

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

        self._script_form.title_edit.editingFinished.connect(self._on_script_title_committed)
        self._script_form.script_path_edit.textChanged.connect(self._on_script_path_changed)
        self._script_form.script_path_edit.editingFinished.connect(self._on_script_path_committed)
        self._script_form.script_path_edit.installEventFilter(self)
        self._script_form.browse_requested.connect(self._on_script_browse_requested)
        self._script_form.auto_send_enter_changed.connect(self._on_script_auto_send_enter_changed)

    def _install_zoom_filters(self) -> None:
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and hasattr(event, "modifiers"):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta:
                    self.adjust_text_zoom(1 if delta > 0 else -1)
                    event.accept()
                    return True
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
            elif obj is self._script_form.script_path_edit and self._script_path_dirty:
                self._flush_script_path()
        return super().eventFilter(obj, event)

    def preferred_width(self) -> int:
        return self._preferred_width

    def set_preferred_width(self, width: int) -> None:
        self._preferred_width = max(MIN_PANEL_WIDTH, min(int(width), MAX_PANEL_WIDTH))

    def text_zoom(self) -> int:
        return self._text_zoom

    def set_text_zoom(self, zoom: int) -> None:
        zoom = max(MIN_TEXT_ZOOM, min(int(zoom), MAX_TEXT_ZOOM))
        if zoom == self._text_zoom:
            return
        self._text_zoom = zoom
        self._apply_text_zoom()
        self.text_zoom_changed.emit(zoom)

    def adjust_text_zoom(self, delta: int) -> None:
        self.set_text_zoom(self._text_zoom + delta)

    def _set_font_size(self, widget: QWidget, size: int, bold: bool = False) -> None:
        font = QFont(widget.font())
        font.setPointSize(max(8, size))
        font.setBold(bold)
        widget.setFont(font)

    def _apply_text_zoom(self) -> None:
        label_size = 12 + self._text_zoom
        field_size = 14 + self._text_zoom
        mono_size = 13 + self._text_zoom
        section_size = 11 + self._text_zoom
        for label in self.findChildren(QLabel):
            self._set_font_size(
                label,
                section_size if label.objectName() == "section_label" else label_size,
                bold=label.objectName() == "section_label",
            )
        for edit in self.findChildren(QLineEdit):
            self._set_font_size(edit, field_size)
        for combo in self.findChildren(QComboBox):
            self._set_font_size(combo, field_size)
        for spin in self.findChildren(QSpinBox):
            self._set_font_size(spin, field_size)
        for button in self.findChildren(QPushButton):
            self._set_font_size(button, field_size)
        for editor in self.findChildren(QPlainTextEdit):
            size = mono_size + 2 if editor.objectName() == "llm_call_output_edit" else mono_size
            self._set_font_size(editor, size)

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
        self._refresh_llm_prompt_preview()

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

    def _on_join_title_committed(self):
        if self._current_node is None:
            return
        new_title = self._join_form.title_edit.text()
        if new_title != self._old_title:
            self.title_committed.emit(self._current_node.node_id, self._old_title, new_title)
            self._old_title = new_title

    def _on_join_count_changed(self, old_count: int, new_count: int):
        if self._current_node is None:
            return
        self.join_count_changed.emit(self._current_node.node_id, old_count, new_count)

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
        self.git_details_changed.emit(self._current_node.node_id)

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
        self.git_details_changed.emit(self._current_node.node_id)

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
        self.git_details_changed.emit(self._current_node.node_id)

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

    def _on_script_title_committed(self):
        if self._current_node is None:
            return
        new_title = self._script_form.title_edit.text()
        if new_title != self._old_title:
            self.title_committed.emit(self._current_node.node_id, self._old_title, new_title)
            self._old_title = new_title

    def _on_script_path_changed(self):
        self._script_path_dirty = True

    def _on_script_path_committed(self):
        if self._script_path_dirty:
            self._flush_script_path()

    def _flush_script_path(self):
        if self._current_node is None:
            return
        self.script_path_committed.emit(self._current_node.node_id, self._script_form.script_path_edit.text())
        self._script_path_dirty = False

    def _on_script_browse_requested(self):
        if self._current_node is None:
            return
        self.script_browse_requested.emit(self._current_node.node_id)

    def _on_script_auto_send_enter_changed(self, checked: bool):
        if self._current_node is None:
            return
        self.script_auto_send_enter_changed.emit(self._current_node.node_id, checked)

    def commit_pending_edits(self) -> None:
        """Commit visible-form edits in a stable order."""
        if self._is_committing:
            return

        from .conditional_node import ConditionalNode
        from .file_op_node import AttentionNode, FileOpNode
        from .git_action_node import GitActionNode
        from .llm_node import LLMNode
        from .control_flow.join_node import JoinNode
        from .loop_node import LoopNode
        from .script_runner import ScriptNode

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
            elif isinstance(self._current_node, ScriptNode):
                if self._script_path_dirty:
                    self._flush_script_path()
                self._on_script_title_committed()
            elif isinstance(self._current_node, ConditionalNode):
                if self._cond_filename_dirty:
                    self._flush_cond_filename()
                self._on_cond_title_committed()
            elif isinstance(self._current_node, LoopNode):
                self._on_loop_title_committed()
            elif isinstance(self._current_node, JoinNode):
                self._on_join_title_committed()
            elif isinstance(self._current_node, GitActionNode):
                if self._git_commit_msg_dirty:
                    self._flush_git_commit_msg()
                if self._git_commit_msg_file_dirty:
                    self._flush_git_commit_msg_file()
                self._on_git_title_committed()
        finally:
            self._is_committing = False

    def show_for_node(self, node) -> None:
        """Load node data into the form and show the matching page."""
        from .conditional_node import ConditionalNode
        from .file_op_node import AttentionNode, FileOpNode
        from .git_action_node import GitActionNode
        from .llm_node import LLMNode
        from .control_flow.join_node import JoinNode
        from .loop_node import LoopNode
        from .script_runner import ScriptNode

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
            self._stack.setCurrentIndex(7)
        elif isinstance(node, ScriptNode):
            self._load_script_form(node)
            self._stack.setCurrentIndex(8)
        elif isinstance(node, LoopNode):
            self._load_loop_form(node)
            self._stack.setCurrentIndex(4)
        elif isinstance(node, JoinNode):
            self._load_join_form(node)
            self._stack.setCurrentIndex(5)
        elif isinstance(node, GitActionNode):
            self._load_git_form(node)
            self._stack.setCurrentIndex(6)
        elif isinstance(node, FileOpNode):
            self._load_file_form(node)
            self._stack.setCurrentIndex(2)
        else:
            self._stack.setCurrentIndex(0)

    def show_overview(self) -> None:
        self.commit_pending_edits()
        self._current_node = None
        self._stack.setCurrentIndex(0)

    def set_overview_text(self, text: str) -> None:
        self._overview_form.summary_edit.setPlainText(text)

    def hide_panel(self) -> None:
        # Kept for call-site compatibility: the panel now stays visible and
        # this method switches to the overview page instead of hiding.
        self.show_overview()

    def maybe_append_output(self, node, line: str) -> None:
        if node is not self._current_node:
            return
        from .conditional_node import ConditionalNode
        from .file_op_node import AttentionNode, FileOpNode
        from .git_action_node import GitActionNode
        from .llm_node import LLMNode
        from .control_flow.join_node import JoinNode
        from .loop_node import LoopNode
        from .script_runner import ScriptNode

        if isinstance(node, LLMNode):
            self._llm_form.show_output(True)
            self._llm_form.append_output_line(line)
        elif isinstance(node, ConditionalNode):
            self._cond_form.show_output(True)
            self._cond_form.output_edit.appendPlainText(line)
        elif isinstance(node, AttentionNode):
            self._attention_form.show_output(True)
            self._attention_form.output_edit.appendPlainText(line)
        elif isinstance(node, ScriptNode):
            self._script_form.show_output(True)
            self._script_form.output_edit.appendPlainText(line)
        elif isinstance(node, LoopNode):
            self._loop_form.show_output(True)
            self._loop_form.output_edit.appendPlainText(line)
        elif isinstance(node, JoinNode):
            self._join_form.show_output(True)
            self._join_form.output_edit.appendPlainText(line)
        elif isinstance(node, GitActionNode):
            self._git_form.show_output(True)
            self._git_form.output_edit.appendPlainText(line)
        elif isinstance(node, FileOpNode):
            self._file_form.show_output(True)
            self._file_form.output_edit.appendPlainText(line)

    def maybe_clear_output(self, node) -> None:
        if node is not self._current_node:
            return
        from .conditional_node import ConditionalNode
        from .file_op_node import AttentionNode, FileOpNode
        from .git_action_node import GitActionNode
        from .llm_node import LLMNode
        from .control_flow.join_node import JoinNode
        from .loop_node import LoopNode
        from .script_runner import ScriptNode

        if isinstance(node, LLMNode):
            self._llm_form.clear_output()
            self._llm_form.show_output(False)
        elif isinstance(node, ConditionalNode):
            self._cond_form.output_edit.clear()
            self._cond_form.show_output(False)
        elif isinstance(node, AttentionNode):
            self._attention_form.output_edit.clear()
            self._attention_form.show_output(False)
        elif isinstance(node, ScriptNode):
            self._script_form.output_edit.clear()
            self._script_form.show_output(False)
        elif isinstance(node, LoopNode):
            self._loop_form.output_edit.clear()
            self._loop_form.show_output(False)
        elif isinstance(node, JoinNode):
            self._join_form.output_edit.clear()
            self._join_form.show_output(False)
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
            form.set_output_text(node.output_text.rstrip("\n"))
            form.show_output(True)
        else:
            form.clear_output()
            form.show_output(False)

        form.title_edit.blockSignals(False)
        form.model_selector.blockSignals(False)
        form.prompt_edit.blockSignals(False)

        self._old_title = node.title
        self._prompt_dirty = False
        self._refresh_llm_prompt_preview()

    def _load_file_form(self, node) -> None:
        form = self._file_form
        form.title_edit.blockSignals(True)
        form.filename_edit.blockSignals(True)

        form.set_op_type(node.node_type)
        form.title_edit.setText(node.title)
        form.filename_edit.setText(node.filename)

        if node.output_text:
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
            form.show_output(True)
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
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
            form.show_output(True)
        else:
            form.output_edit.clear()
            form.show_output(False)

        form.title_edit.blockSignals(False)
        self._old_title = node.title

    def _load_join_form(self, node) -> None:
        form = self._join_form
        form.title_edit.blockSignals(True)

        form.title_edit.setText(node.title)
        form.set_wait_for_count(node.wait_for_count)

        if node.output_text:
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
            form.show_output(True)
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
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
            form.show_output(True)
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
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
            form.show_output(True)
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
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
            form.show_output(True)
        else:
            form.output_edit.clear()
            form.show_output(False)

        form.title_edit.blockSignals(False)
        form.message_edit.blockSignals(False)

        self._old_title = node.title
        self._attention_message_dirty = False

    def _load_script_form(self, node) -> None:
        form = self._script_form
        form.title_edit.blockSignals(True)
        form.script_path_edit.blockSignals(True)
        form.auto_send_enter_checkbox.blockSignals(True)

        form.title_edit.setText(node.title)
        form.script_path_edit.setText(node.script_path)
        form.auto_send_enter_checkbox.setChecked(bool(node.auto_send_enter))

        if node.output_text:
            form.output_edit.setPlainText(node.output_text.rstrip("\n"))
            form.show_output(True)
        else:
            form.output_edit.clear()
            form.show_output(False)

        form.title_edit.blockSignals(False)
        form.script_path_edit.blockSignals(False)
        form.auto_send_enter_checkbox.blockSignals(False)

        self._old_title = node.title
        self._script_path_dirty = False

    def refresh_if_current(self, node) -> None:
        """Reload form fields if this node is currently shown."""
        if node is not self._current_node:
            return
        self.show_for_node(node)

    def set_prompt_injection_preview_context(
        self,
        prepend_template_contents: Sequence[str],
        append_template_contents: Sequence[str],
        one_off_text: str = "",
        one_off_placement: str = "append",
    ) -> None:
        prepend_sections: list[str] = []
        append_sections: list[str] = []
        for section in prepend_template_contents:
            normalized = str(section).strip()
            if normalized:
                prepend_sections.append(normalized)
        for section in append_template_contents:
            normalized = str(section).strip()
            if normalized:
                append_sections.append(normalized)
        self._preview_prepend_templates = prepend_sections
        self._preview_append_templates = append_sections
        self._preview_one_off_text = one_off_text or ""
        self._preview_one_off_placement = one_off_placement or "append"
        self._refresh_llm_prompt_preview()

    def _refresh_llm_prompt_preview(self) -> None:
        from .llm_node import LLMNode

        if not isinstance(self._current_node, LLMNode):
            return
        preview_text = compose_prompt(
            self._llm_form.prompt_edit.toPlainText(),
            self._preview_prepend_templates,
            self._preview_append_templates,
            self._preview_one_off_text,
            self._preview_one_off_placement,
        )
        self._llm_form.prompt_preview_edit.setPlainText(preview_text)
