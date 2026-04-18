"""Node-form loading and output helpers for PropertiesPanel."""

from __future__ import annotations

from src.gui.conditional_node import ConditionalNode
from src.gui.control_flow.join_node import JoinNode
from src.gui.file_op_node import AttentionNode, FileOpNode
from src.gui.git_action_node import GitActionNode
from src.gui.llm_node import LLMNode
from src.gui.loop_node import LoopNode
from src.gui.script_runner import ScriptNode
from src.gui.variables import VariableNode


def append_node_output(panel, node, line: str) -> None:
    if isinstance(node, LLMNode):
        panel._llm_form.show_output(True)
        panel._llm_form.append_output_line(line)
    elif isinstance(node, ConditionalNode):
        panel._cond_form.show_output(True)
        panel._cond_form.output_edit.appendPlainText(line)
    elif isinstance(node, AttentionNode):
        panel._attention_form.show_output(True)
        panel._attention_form.output_edit.appendPlainText(line)
    elif isinstance(node, ScriptNode):
        panel._script_form.show_output(True)
        panel._script_form.output_edit.appendPlainText(line)
    elif isinstance(node, LoopNode):
        panel._loop_form.show_output(True)
        panel._loop_form.output_edit.appendPlainText(line)
    elif isinstance(node, JoinNode):
        panel._join_form.show_output(True)
        panel._join_form.output_edit.appendPlainText(line)
    elif isinstance(node, GitActionNode):
        panel._git_form.show_output(True)
        panel._git_form.output_edit.appendPlainText(line)
    elif isinstance(node, VariableNode):
        panel._variable_form.show_output(True)
        panel._variable_form.output_edit.appendPlainText(line)
    elif isinstance(node, FileOpNode):
        panel._file_form.show_output(True)
        panel._file_form.output_edit.appendPlainText(line)


def clear_node_output(panel, node) -> None:
    if isinstance(node, LLMNode):
        panel._llm_form.clear_output()
        panel._llm_form.show_output(False)
    elif isinstance(node, ConditionalNode):
        panel._cond_form.output_edit.clear()
        panel._cond_form.show_output(False)
    elif isinstance(node, AttentionNode):
        panel._attention_form.output_edit.clear()
        panel._attention_form.show_output(False)
    elif isinstance(node, ScriptNode):
        panel._script_form.output_edit.clear()
        panel._script_form.show_output(False)
    elif isinstance(node, LoopNode):
        panel._loop_form.output_edit.clear()
        panel._loop_form.show_output(False)
    elif isinstance(node, JoinNode):
        panel._join_form.output_edit.clear()
        panel._join_form.show_output(False)
    elif isinstance(node, GitActionNode):
        panel._git_form.output_edit.clear()
        panel._git_form.show_output(False)
    elif isinstance(node, VariableNode):
        panel._variable_form.output_edit.clear()
        panel._variable_form.show_output(False)
    elif isinstance(node, FileOpNode):
        panel._file_form.output_edit.clear()
        panel._file_form.show_output(False)


def load_file_form(panel, node) -> None:
    form = panel._file_form
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
    panel._old_title = node.title
    panel._filename_dirty = False


def load_loop_form(panel, node) -> None:
    form = panel._loop_form
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
    panel._old_title = node.title


def load_join_form(panel, node) -> None:
    form = panel._join_form
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
    panel._old_title = node.title


def load_cond_form(panel, node) -> None:
    form = panel._cond_form
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
    panel._old_title = node.title
    panel._cond_filename_dirty = False


def load_git_form(panel, node) -> None:
    form = panel._git_form
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
    panel._old_title = node.title
    panel._git_commit_msg_dirty = False
    panel._git_commit_msg_file_dirty = False


def load_attention_form(panel, node) -> None:
    form = panel._attention_form
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
    panel._old_title = node.title
    panel._attention_message_dirty = False


def load_script_form(panel, node) -> None:
    form = panel._script_form
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
    panel._old_title = node.title
    panel._script_path_dirty = False


def load_variable_form(panel, node) -> None:
    form = panel._variable_form
    form.title_edit.blockSignals(True)
    form.variable_name_edit.blockSignals(True)
    form.variable_type_combo.blockSignals(True)
    form.value_edit.blockSignals(True)
    form.title_edit.setText(node.title)
    form.variable_name_edit.setText(node.variable_name)
    form.set_variable_type(node.variable_type)
    form.value_edit.setPlainText(node.variable_value)
    panel._pending_variable_warning_name = node.variable_name
    warning_text = ""
    if panel._variable_warning_provider is not None:
        warning_text = panel._variable_warning_provider(node)
    form.set_warning_text(warning_text)
    if node.output_text:
        form.output_edit.setPlainText(node.output_text.rstrip("\n"))
        form.show_output(True)
    else:
        form.output_edit.clear()
        form.show_output(False)
    form.title_edit.blockSignals(False)
    form.variable_name_edit.blockSignals(False)
    form.variable_type_combo.blockSignals(False)
    form.value_edit.blockSignals(False)
    panel._old_title = node.title
    panel._variable_name_dirty = False
    panel._variable_value_dirty = False
