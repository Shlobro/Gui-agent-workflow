"""_ExecutionMixin - workflow run/stop logic for WorkflowCanvas."""

import os
import re
from collections import deque
from typing import TYPE_CHECKING, Dict, List, Sequence
from uuid import uuid4

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from src.llm.prompt_injection import compose_prompt
from src.workers.llm_worker import LLMWorker
from src.workers.git_worker import GitWorker
from src.gui.file_op_node import AttentionNode, FileOpNode
from src.gui.conditional_node import (
    CONDITION_REGISTRY,
    ConditionalNode,
    condition_display_name,
    condition_execution_mode,
    condition_requires_filename,
)
from src.gui.control_flow.join_node import JoinNode
from src.gui.llm_node import LLMNode, StartNode, WorkflowNode
from src.gui.workflow_io import get_provider_for_model

if TYPE_CHECKING:
    from src.gui.canvas import WorkflowCanvas

GraphNode = WorkflowNode

_USAGE_LIMIT_RE = re.compile(
    r"you'?ve hit your usage limit"
    r"|you'?ve hit your limit"
    r"|you'?ve reached your \d+-hour message limit"
    r"|you'?ve reached your rate limit"
    r"|claude usage limit reached"
    r"|ratelimiterror"
    r"|insufficient_quota"
    r"|rate_limit_error"
    r"|api error: rate limit (?:reached|exceeded)"
    r"|rate limit reached for requests"
    r"|rate limit reached for"
    r"|resource_exhausted"
    r"|resource has been exhausted \(e\.g\. check quota\)"
    r"|quota_exhausted"
    r"|terminalquotaerror"
    r"|you have exhausted your capacity on this model"
    r"|exhausted your capacity on this model"
    r"|quota will reset after"
    r"|you exceeded your current quota"
    r"|usage limit reached for"
    r"|quota exceeded for",
    re.IGNORECASE,
)

_GIT_STATUS_TIMEOUT_SECONDS = 15
_GIT_STATUS_COMMAND = ["git", "status", "--porcelain", "--untracked-files=all"]


def is_usage_limit_error(text: str) -> bool:
    return bool(_USAGE_LIMIT_RE.search(text))


class _ExecutionMixin:
    """Run/stop execution methods mixed into WorkflowCanvas."""

    # ------------------------------------------------------------------
    # Pre-run checks
    # ------------------------------------------------------------------

    def _check_project_folder(self: "WorkflowCanvas") -> bool:
        if self._working_directory:
            return True
        QMessageBox.warning(
            self, "No Project Folder",
            "Please open a project folder before running a workflow.\n\n"
            "Use File -> Open Project Folder... to choose one.",
        )
        return False

    # ------------------------------------------------------------------
    # Public run modes
    # ------------------------------------------------------------------

    def run_all(self: "WorkflowCanvas"):
        if not self._check_project_folder():
            return
        reachable = self._reachable_from(self._start_node)
        nodes = [n for n in reachable if not isinstance(n, StartNode)]
        if not nodes:
            self.status_update.emit("Nothing to run \u2014 connect nodes to Start first.")
            return
        errors = self._validate_nodes(nodes)
        if errors:
            QMessageBox.warning(
                self, "Cannot Run",
                "Fix these issues before running:\n\n" + "\n".join(errors),
            )
            return
        self._run_workflow(nodes, roots=self._direct_children(self._start_node))

    def run_selected_only(self: "WorkflowCanvas"):
        if not self._check_project_folder():
            return
        selected = [
            i for i in self._scene.selectedItems()
            if isinstance(i, WorkflowNode) and not isinstance(i, StartNode)
        ]
        if not selected:
            QMessageBox.information(self, "No Selection", "Select at least one node first.")
            return
        if len(selected) > 1:
            reply = QMessageBox.question(
                self, "Run Multiple",
                f"Run {len(selected)} selected nodes simultaneously (without fan-out)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        errors = self._validate_nodes(selected)
        if errors:
            QMessageBox.warning(
                self, "Cannot Run",
                "Fix these issues before running:\n\n" + "\n".join(errors),
            )
            return
        self._run_workflow(selected, roots=list(selected), no_fanout=True)

    def run_from_here(self: "WorkflowCanvas"):
        if not self._check_project_folder():
            return
        selected = [
            i for i in self._scene.selectedItems()
            if isinstance(i, WorkflowNode) and not isinstance(i, StartNode)
        ]
        if len(selected) != 1:
            return
        start = selected[0]
        reachable = self._reachable_from(start)
        nodes = [n for n in reachable if not isinstance(n, StartNode)]
        errors = self._validate_nodes(nodes)
        if errors:
            QMessageBox.warning(
                self, "Cannot Run",
                "Fix these issues before running:\n\n" + "\n".join(errors),
            )
            return
        self._run_workflow(nodes, roots=[start])

    def stop_all(self: "WorkflowCanvas"):
        self._running = False
        self.run_state_changed.emit(False)
        self._no_fanout = False
        self._pending_child_triggers = 0
        self._seeding_roots = False
        self._loop_counters.clear()
        self._join_wait_counts.clear()
        self._pending_join_waits = 0
        self._llm_invocation_counts.clear()
        self._exec_streamed_output.clear()
        self._exec_lineage.clear()
        for worker in list(self._active_workers.values()):
            if worker is not None:
                worker.cancel()
        for node in self._nodes.values():
            if node.status in {"running", "looping"}:
                node.set_status("idle")
        self.status_update.emit("Stopped.")

    # ------------------------------------------------------------------
    # Graph traversal / validation helpers
    # ------------------------------------------------------------------

    def _reachable_from(self: "WorkflowCanvas", start) -> list:
        visited = []
        queue = deque([start])
        seen = {start.node_id}
        while queue:
            node = queue.popleft()
            visited.append(node)
            for conn in node.connections():
                if conn.source_node is node:
                    nxt = conn.target_node
                    if nxt.node_id not in seen:
                        seen.add(nxt.node_id)
                        queue.append(nxt)
        return visited

    def _would_create_cycle(self: "WorkflowCanvas", source, target: GraphNode) -> bool:
        return source in self._reachable_from(target)

    def _source_port_has_outgoing(self: "WorkflowCanvas", source, port: str = "output") -> bool:
        """Return True if source already has an outgoing connection on the given port."""
        return any(
            conn.source_node is source
            and getattr(conn, "source_port", "output") == port
            for conn in self._connections
        )

    def _node_validation_errors(self: "WorkflowCanvas", node: GraphNode) -> List[str]:
        from src.gui.loop_node import LoopNode
        from src.gui.git_action_node import GitActionNode

        valid_git_actions = {"git_add", "git_commit", "git_push"}
        valid_msg_sources = {"static", "from_file"}
        reasons: List[str] = []

        if isinstance(node, ConditionalNode):
            if condition_requires_filename(node.condition_type) and not node.filename.strip():
                reasons.append("has no filename set")
            if node.condition_type not in CONDITION_REGISTRY:
                reasons.append(f'has unknown condition type "{node.condition_type}"')
            return reasons

        if isinstance(node, AttentionNode):
            if not node.message_text.strip():
                reasons.append("has no attention message set")
            return reasons

        if isinstance(node, FileOpNode):
            if not node.filename.strip():
                reasons.append("has no filename set")
            return reasons

        if isinstance(node, LoopNode):
            # loop_count is always clamped by constructor/load path
            return reasons

        if isinstance(node, JoinNode):
            return reasons

        if isinstance(node, GitActionNode):
            if node.git_action not in valid_git_actions:
                reasons.append(f'has unknown git action "{node.git_action}"')
                return reasons
            if node.msg_source not in valid_msg_sources:
                reasons.append(f'has unknown message source "{node.msg_source}"')
                return reasons
            if node.git_action == "git_commit":
                if node.msg_source == "static" and not node.commit_msg.strip():
                    reasons.append("has no commit message set")
                elif node.msg_source == "from_file" and not node.commit_msg_file.strip():
                    reasons.append("has no commit message file set")
            return reasons

        if not node.prompt_text.strip():
            reasons.append("has no prompt")
        if not node.model_id:
            reasons.append("has no model selected")
        elif get_provider_for_model(node.model_id) is None:
            reasons.append(f'has unknown model "{node.model_id}"')
        return reasons

    def _validation_errors_by_node(
        self: "WorkflowCanvas", nodes: Sequence[GraphNode]
    ) -> Dict[str, List[str]]:
        errors: Dict[str, List[str]] = {}
        for node in nodes:
            reasons = self._node_validation_errors(node)
            if reasons:
                errors[node.node_id] = reasons
        return errors

    def refresh_node_validation_state(self: "WorkflowCanvas") -> Dict[str, List[str]]:
        """Update each canvas node's invalid marker based on current run validation rules."""
        errors_by_node = self._validation_errors_by_node(list(self._nodes.values()))
        for node in self._nodes.values():
            node.set_invalid(node.node_id in errors_by_node)
        return errors_by_node

    def _validate_nodes(self: "WorkflowCanvas", nodes: Sequence[GraphNode]) -> List[str]:
        errors_by_node = self.refresh_node_validation_state()
        errors: List[str] = []
        for node in nodes:
            title = getattr(node, "title", node.node_id)
            for reason in errors_by_node.get(node.node_id, []):
                errors.append(f'\u2022 "{title}" {reason}.')
        return errors

    def _direct_children(self: "WorkflowCanvas", node) -> list:
        return [
            conn.target_node for conn in self._connections
            if conn.source_node is node
        ]

    # ------------------------------------------------------------------
    # Internal run engine
    # ------------------------------------------------------------------

    def _run_workflow(self: "WorkflowCanvas", nodes: list, roots: list, no_fanout: bool = False):
        if self._running:
            return
        self._llm_invocation_counts.clear()
        self._exec_streamed_output.clear()
        self._join_wait_counts.clear()
        self._pending_join_waits = 0
        for node in nodes:
            node.set_status("idle")
            node.clear_output()
            if self.on_output_cleared:
                self.on_output_cleared(node)
        self._running = True
        self.run_state_changed.emit(True)
        self._no_fanout = no_fanout
        self._run_id += 1
        self._current_run_exec_ids.clear()
        self._pending_child_triggers = 0
        self._seeding_roots = True
        n = len(roots)
        self.status_update.emit(f"Running\u2026 ({n} node{'s' if n != 1 else ''} triggered)")
        try:
            shared_join_token = str(uuid4()) if len(roots) > 1 and not no_fanout else ""
            for node in roots:
                lineage_token = str(uuid4())
                root_join_token = shared_join_token or lineage_token
                self._trigger_node(node, lineage_token, join_token=root_join_token)
        finally:
            self._seeding_roots = False
        self._check_drain()

    def _trigger_node(self: "WorkflowCanvas", node: GraphNode, lineage_token: str = "",
                      loop_token: str = "", join_token: str = ""):
        if not self._running:
            return
        self._exec_counter += 1
        if not lineage_token:
            lineage_token = str(uuid4())
        self._fire_invocation(node, self._exec_counter, lineage_token, loop_token, join_token)

    def _fire_invocation(self: "WorkflowCanvas", node: GraphNode, exec_id: int,
                         lineage_token: str = "", loop_token: str = "", join_token: str = ""):
        from src.gui.loop_node import LoopNode
        self._active_workers[exec_id] = None
        self._exec_node[exec_id] = node.node_id
        self._exec_lineage[exec_id] = lineage_token
        self._current_run_exec_ids.add(exec_id)
        if isinstance(node, LoopNode):
            node.set_status("looping")
            self._fire_loop(node, exec_id, lineage_token, loop_token, join_token)
            return
        if isinstance(node, JoinNode):
            node.set_status("running")
            self._fire_join(node, exec_id, lineage_token, loop_token, join_token)
            return
        node.set_status("running")
        if isinstance(node, ConditionalNode):
            self._fire_condition_check(node, exec_id, lineage_token, loop_token, join_token)
            return
        if isinstance(node, AttentionNode):
            self._fire_attention(node, exec_id, lineage_token, loop_token, join_token)
            return
        if isinstance(node, FileOpNode):
            self._fire_file_op(node, exec_id, lineage_token, loop_token, join_token)
            return
        from src.gui.git_action_node import GitActionNode
        if isinstance(node, GitActionNode):
            self._fire_git_action(node, exec_id, lineage_token, loop_token, join_token)
            return
        model_id = node.model_id
        if not model_id:
            node.append_output("[Error] No model selected.")
            if self.on_output_line:
                self.on_output_line(node, "[Error] No model selected.")
            node.set_status("error")
            del self._active_workers[exec_id]
            self._exec_node.pop(exec_id, None)
            self._exec_lineage.pop(exec_id, None)
            self._current_run_exec_ids.discard(exec_id)
            return
        provider = get_provider_for_model(model_id)
        if provider is None:
            msg = f"[Error] Unknown model: {model_id}"
            node.append_output(msg)
            if self.on_output_line:
                self.on_output_line(node, msg)
            node.set_status("error")
            del self._active_workers[exec_id]
            self._exec_node.pop(exec_id, None)
            self._exec_lineage.pop(exec_id, None)
            self._current_run_exec_ids.discard(exec_id)
            return

        composed_prompt = compose_prompt(
            node.prompt_text,
            self._prompt_injection_prepend_templates,
            self._prompt_injection_append_templates,
            self._prompt_injection_one_off,
            self._prompt_injection_one_off_placement,
        )
        self._start_llm_output_block(node)
        worker = LLMWorker(
            provider,
            composed_prompt,
            model=model_id,
            working_directory=self._working_directory,
        )
        self._active_workers[exec_id] = worker
        self._exec_streamed_output[exec_id] = False
        run_id = self._run_id

        def on_output(line: str, _n=node, _e=exec_id, _r=run_id):
            if _r == self._run_id and self._running and _e in self._active_workers and _e not in self._retired_exec_ids:
                self._exec_streamed_output[_e] = True
                _n.append_output(line)
                if self.on_output_line:
                    self.on_output_line(_n, line)

        def on_finished(
            full: str,
            _n=node,
            _e=exec_id,
            _r=run_id,
            _lt=lineage_token,
            _lp=loop_token,
            _jt=join_token,
        ):
            self._on_invocation_done(
                _n,
                _e,
                full,
                error=False,
                run_id=_r,
                lineage_token=_lt,
                loop_token=_lp,
                join_token=_jt,
            )

        def on_error(
            msg: str,
            _n=node,
            _e=exec_id,
            _r=run_id,
            _lt=lineage_token,
            _lp=loop_token,
            _jt=join_token,
        ):
            self._on_invocation_done(
                _n,
                _e,
                msg,
                error=True,
                run_id=_r,
                lineage_token=_lt,
                loop_token=_lp,
                join_token=_jt,
            )

        worker.output_line.connect(on_output)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    def _start_llm_output_block(self: "WorkflowCanvas", node: LLMNode) -> None:
        call_index = self._llm_invocation_counts.get(node.node_id, 0) + 1
        self._llm_invocation_counts[node.node_id] = call_index
        if node.output_text.strip():
            node.append_output("")
            if self.on_output_line:
                self.on_output_line(node, "")
        header = f"=== Call {call_index} ==="
        node.append_output(header)
        if self.on_output_line:
            self.on_output_line(node, header)

    def _fire_condition_check(self: "WorkflowCanvas", node: ConditionalNode, exec_id: int,
                              lineage_token: str = "", loop_token: str = "", join_token: str = ""):
        run_id = self._run_id
        try:
            resolved_path = None
            if condition_requires_filename(node.condition_type):
                resolved_path = self._resolve_file_op_path(node.filename)
            if condition_execution_mode(node.condition_type) == "git_worker":
                self._fire_git_changes_condition(
                    node,
                    exec_id,
                    run_id,
                    lineage_token=lineage_token,
                    loop_token=loop_token,
                    join_token=join_token,
                )
                return
            result = node.evaluate(
                resolved_path=resolved_path,
                working_directory=self._working_directory or "",
            )
            branch = "true" if result else "false"
            display_name = condition_display_name(node.condition_type)
            node.append_output(f"Condition '{display_name}': {branch}")
            if self.on_output_line:
                self.on_output_line(node, f"Condition '{display_name}': {branch}")
            self._on_condition_done(
                node,
                exec_id,
                branch,
                run_id=run_id,
                lineage_token=lineage_token,
                loop_token=loop_token,
                join_token=join_token,
            )
        except Exception as exc:
            self._on_invocation_done(
                node,
                exec_id,
                str(exc),
                error=True,
                run_id=run_id,
                lineage_token=lineage_token,
                loop_token=loop_token,
                join_token=join_token,
            )

    def _fire_git_changes_condition(
        self: "WorkflowCanvas",
        node: ConditionalNode,
        exec_id: int,
        run_id: int,
        lineage_token: str = "",
        loop_token: str = "",
        join_token: str = "",
    ):
        cwd = self._working_directory or ""
        if not cwd:
            self._on_invocation_done(
                node,
                exec_id,
                "No project folder selected.",
                error=True,
                run_id=run_id,
                lineage_token=lineage_token,
                loop_token=loop_token,
            )
            return

        worker = GitWorker(
            command=_GIT_STATUS_COMMAND,
            working_directory=cwd,
            timeout=_GIT_STATUS_TIMEOUT_SECONDS,
        )
        self._active_workers[exec_id] = worker

        def on_output(line: str, _n=node, _e=exec_id, _r=run_id):
            if (
                _r == self._run_id
                and self._running
                and _e in self._active_workers
                and _e not in self._retired_exec_ids
            ):
                _n.append_output(line)
                if self.on_output_line:
                    self.on_output_line(_n, line)

        def on_finished(
            full: str, _n=node, _e=exec_id, _r=run_id, _lt=lineage_token, _lp=loop_token, _jt=join_token
        ):
            branch = "true" if bool(full.strip()) else "false"
            display_name = condition_display_name(_n.condition_type)
            if (
                _r == self._run_id
                and self._running
                and _e in self._active_workers
                and _e not in self._retired_exec_ids
            ):
                _n.append_output(f"Condition '{display_name}': {branch}")
                if self.on_output_line:
                    self.on_output_line(_n, f"Condition '{display_name}': {branch}")
            self._on_condition_done(
                _n,
                _e,
                branch,
                run_id=_r,
                lineage_token=_lt,
                loop_token=_lp,
                join_token=_jt,
            )

        def on_error(
            msg: str, _n=node, _e=exec_id, _r=run_id, _lt=lineage_token, _lp=loop_token, _jt=join_token
        ):
            if msg.startswith("Timed out after "):
                msg = (
                    "git status timed out after "
                    f"{_GIT_STATUS_TIMEOUT_SECONDS}s while checking for repository changes."
                )
            self._on_invocation_done(
                _n,
                _e,
                msg,
                error=True,
                run_id=_r,
                lineage_token=_lt,
                loop_token=_lp,
                join_token=_jt,
            )

        worker.output_line.connect(on_output)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    def _fire_attention(self: "WorkflowCanvas", node: AttentionNode, exec_id: int,
                        lineage_token: str = "", loop_token: str = "", join_token: str = ""):
        run_id = self._run_id
        message = node.message_text.strip()
        QApplication.beep()
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Attention Required")
        dialog.setText(node.title)
        dialog.setInformativeText(message)
        continue_button = dialog.addButton(
            "Continue Workflow", QMessageBox.ButtonRole.AcceptRole
        )
        dialog.addButton(
            "Stop Workflow", QMessageBox.ButtonRole.RejectRole
        )
        dialog.setDefaultButton(continue_button)
        dialog.exec()
        if dialog.clickedButton() is not continue_button:
            if exec_id not in self._active_workers:
                return
            self._retired_exec_ids.discard(exec_id)
            del self._active_workers[exec_id]
            self._exec_node.pop(exec_id, None)
            self._exec_lineage.pop(exec_id, None)
            self._current_run_exec_ids.discard(exec_id)
            choice = "Attention acknowledged: workflow stopped by user."
            node.clear_output()
            if self.on_output_cleared:
                self.on_output_cleared(node)
            node.append_output(choice)
            if self.on_output_line:
                self.on_output_line(node, choice)
            self.stop_all()
            node.set_status("done")
            self.status_update.emit(f'Stopped at "{node.title}".')
            return
        self._on_invocation_done(
            node,
            exec_id,
            "Attention acknowledged: continuing workflow.",
            error=False,
            run_id=run_id,
            lineage_token=lineage_token,
            loop_token=loop_token,
            join_token=join_token,
        )

    def _on_condition_done(self: "WorkflowCanvas", node: ConditionalNode, exec_id: int,
                           branch: str, run_id: int = 0, lineage_token: str = "",
                           loop_token: str = "", join_token: str = ""):
        """Complete a ConditionalNode invocation and queue only the matching branch."""
        if exec_id not in self._active_workers:
            return
        retired = exec_id in self._retired_exec_ids
        self._retired_exec_ids.discard(exec_id)
        del self._active_workers[exec_id]
        self._exec_node.pop(exec_id, None)
        self._exec_lineage.pop(exec_id, None)
        self._current_run_exec_ids.discard(exec_id)
        if run_id != self._run_id or not self._running:
            self._check_drain()
            return
        if retired:
            self._check_drain()
            return
        node.set_status("done")
        if not self._no_fanout:
            self._queue_child_triggers(node, run_id, branch=branch,
                                       lineage_token=lineage_token, loop_token=loop_token, join_token=join_token)
        self._check_drain()

    def _fire_loop(self: "WorkflowCanvas", node, exec_id: int, lineage_token: str,
                   loop_token: str = "", join_token: str = ""):
        run_id = self._run_id
        # loop_token is stable for the lifetime of this loop thread; assign on first entry.
        if not loop_token:
            loop_token = lineage_token
        key = (node.node_id, loop_token)
        count = self._loop_counters.get(key, 0) + 1
        if count <= node.loop_count:
            line = f"Loop iteration {count}/{node.loop_count}"
            node.append_output(line)
            if self.on_output_line:
                self.on_output_line(node, line)
            self._loop_counters[key] = count
            self._on_loop_iteration(node, exec_id, "loop", lineage_token, loop_token, join_token, run_id)
        else:
            self._loop_counters.pop(key, None)
            self._on_loop_iteration(node, exec_id, "done", lineage_token, loop_token, join_token, run_id)

    def _on_loop_iteration(self: "WorkflowCanvas", node, exec_id: int, branch: str,
                           lineage_token: str, loop_token: str, join_token: str, run_id: int):
        """Complete a LoopNode invocation and queue only the correct branch."""
        if exec_id not in self._active_workers:
            return
        retired = exec_id in self._retired_exec_ids
        self._retired_exec_ids.discard(exec_id)
        del self._active_workers[exec_id]
        self._exec_node.pop(exec_id, None)
        self._exec_lineage.pop(exec_id, None)
        self._current_run_exec_ids.discard(exec_id)
        if run_id != self._run_id or not self._running:
            self._check_drain()
            return
        if retired:
            self._check_drain()
            return
        if branch == "loop":
            node.set_status("looping")
        if branch == "done":
            node.set_status("done")
        if not self._no_fanout:
            # For the loop branch, pass loop_token so the counter key survives fan-out
            # on downstream nodes before re-entering this loop node.
            child_loop_token = loop_token if branch == "loop" else ""
            children_queued = self._queue_child_triggers(
                node, run_id, branch=branch,
                lineage_token=lineage_token, loop_token=child_loop_token, join_token=join_token,
            )
            # No outgoing connections on the loop branch means the loop can
            # never iterate - mark done so the node does not stay visually "running".
            if branch == "loop" and children_queued == 0:
                self._loop_counters.pop((node.node_id, loop_token), None)
                node.set_status("done")
        else:
            # Run Selected / no-fanout: loop cannot iterate, clear counter and mark done.
            self._loop_counters.pop((node.node_id, loop_token), None)
            node.set_status("done")
        self._check_drain()

    def _join_group_key(self, lineage_token: str, join_token: str) -> str:
        return join_token or lineage_token or f"run-{self._run_id}"

    def _clear_join_state_for_node(self, node_id: str) -> None:
        for key, count in list(self._join_wait_counts.items()):
            if key[0] != node_id:
                continue
            self._pending_join_waits = max(0, self._pending_join_waits - count)
            self._join_wait_counts.pop(key, None)

    def _has_pending_join_waits_for_node(self, node_id: str) -> bool:
        return any(key[0] == node_id for key in self._join_wait_counts)

    def _fire_join(
        self: "WorkflowCanvas",
        node: JoinNode,
        exec_id: int,
        lineage_token: str = "",
        loop_token: str = "",
        join_token: str = "",
    ) -> None:
        run_id = self._run_id
        group_key = self._join_group_key(lineage_token, join_token)
        join_key = (node.node_id, group_key)
        current_count = self._join_wait_counts.get(join_key, 0) + 1
        self._join_wait_counts[join_key] = current_count
        self._pending_join_waits += 1

        if current_count < node.wait_for_count:
            line = f"Join waiting: {current_count}/{node.wait_for_count}"
            node.append_output(line)
            if self.on_output_line:
                self.on_output_line(node, line)
            self._on_join_waiting(node, exec_id, run_id=run_id)
            return

        remainder = current_count - node.wait_for_count
        if remainder > 0:
            self._join_wait_counts[join_key] = remainder
        else:
            self._join_wait_counts.pop(join_key, None)
        self._pending_join_waits = max(0, self._pending_join_waits - node.wait_for_count)
        line = f"Join released: {node.wait_for_count}/{node.wait_for_count}"
        node.append_output(line)
        if self.on_output_line:
            self.on_output_line(node, line)
        released_lineage = str(uuid4())
        self._on_join_release(
            node,
            exec_id,
            run_id=run_id,
            lineage_token=released_lineage,
            loop_token=loop_token,
        )

    def _on_join_waiting(self: "WorkflowCanvas", node: JoinNode, exec_id: int, run_id: int = 0) -> None:
        if exec_id not in self._active_workers:
            return
        retired = exec_id in self._retired_exec_ids
        self._retired_exec_ids.discard(exec_id)
        del self._active_workers[exec_id]
        self._exec_node.pop(exec_id, None)
        self._exec_lineage.pop(exec_id, None)
        self._current_run_exec_ids.discard(exec_id)
        if run_id != self._run_id or not self._running or retired:
            self._check_drain()
            return
        node.set_status("running")
        self._check_drain()

    def _on_join_release(
        self: "WorkflowCanvas",
        node: JoinNode,
        exec_id: int,
        run_id: int = 0,
        lineage_token: str = "",
        loop_token: str = "",
    ) -> None:
        if exec_id not in self._active_workers:
            return
        retired = exec_id in self._retired_exec_ids
        self._retired_exec_ids.discard(exec_id)
        del self._active_workers[exec_id]
        self._exec_node.pop(exec_id, None)
        self._exec_lineage.pop(exec_id, None)
        self._current_run_exec_ids.discard(exec_id)
        if run_id != self._run_id or not self._running or retired:
            self._check_drain()
            return
        if self._has_pending_join_waits_for_node(node.node_id):
            node.set_status("running")
        else:
            node.set_status("done")
        if not self._no_fanout:
            self._queue_child_triggers(
                node,
                run_id,
                lineage_token=lineage_token,
                loop_token=loop_token,
                join_token="",
            )
        self._check_drain()

    def _resolve_file_op_path(self: "WorkflowCanvas", filename: str) -> str:
        if not self._working_directory:
            raise ValueError("No project folder selected.")
        raw = filename.strip()
        if not raw:
            raise ValueError("Filename is empty.")
        drive, _ = os.path.splitdrive(raw)
        if os.path.isabs(raw) or drive:
            raise ValueError("Filename must be relative to the selected project folder.")
        project_root = os.path.realpath(self._working_directory)
        target = os.path.realpath(os.path.join(project_root, raw))
        try:
            common = os.path.commonpath([project_root, target])
        except ValueError as exc:
            raise ValueError("Filename escapes the selected project folder.") from exc
        if os.path.normcase(common) != os.path.normcase(project_root):
            raise ValueError("Filename escapes the selected project folder.")
        if os.path.normcase(target) == os.path.normcase(project_root):
            raise ValueError("Filename must point to a file inside the project folder.")
        return target

    def _fire_file_op(self: "WorkflowCanvas", node: FileOpNode, exec_id: int,
                      lineage_token: str = "", loop_token: str = "", join_token: str = ""):
        run_id = self._run_id
        filename = node.filename.strip()
        try:
            filepath = self._resolve_file_op_path(filename)
            op = node.node_type
            if op == "create_file":
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                if os.path.exists(filepath):
                    if not os.path.isfile(filepath):
                        raise IsADirectoryError(f"Cannot create file at non-file path: {filepath}")
                    result = f"Already exists: {filepath}"
                else:
                    with open(filepath, "w", encoding="utf-8"):
                        pass
                    result = f"Created: {filepath}"
            elif op == "truncate_file":
                with open(filepath, "w", encoding="utf-8"):
                    pass
                result = f"Truncated: {filepath}"
            elif op == "delete_file":
                os.remove(filepath)
                result = f"Deleted: {filepath}"
            else:
                raise ValueError(f"Unknown file op: {op}")
            self._on_invocation_done(
                node,
                exec_id,
                result,
                error=False,
                run_id=run_id,
                lineage_token=lineage_token,
                loop_token=loop_token,
                join_token=join_token,
            )
        except Exception as exc:
            self._on_invocation_done(
                node,
                exec_id,
                str(exc),
                error=True,
                run_id=run_id,
                lineage_token=lineage_token,
                loop_token=loop_token,
                join_token=join_token,
            )

    def _fire_git_action(self: "WorkflowCanvas", node, exec_id: int,
                         lineage_token: str = "", loop_token: str = "", join_token: str = ""):
        run_id = self._run_id
        cwd = self._working_directory or os.getcwd()
        try:
            action = node.git_action
            if action == "git_add":
                command = ["git", "add", "."]
            elif action == "git_commit":
                if node.msg_source == "from_file":
                    msg_path = self._resolve_file_op_path(node.commit_msg_file)
                    with open(msg_path, "r", encoding="utf-8") as fh:
                        message = fh.read().strip()
                else:
                    message = node.commit_msg.strip()
                if not message:
                    raise ValueError("Commit message is empty.")
                command = ["git", "commit", "-m", message]
            elif action == "git_push":
                command = ["git", "push"]
            else:
                raise ValueError(f"Unknown git action: {action}")
        except Exception as exc:
            self._on_invocation_done(
                node,
                exec_id,
                str(exc),
                error=True,
                run_id=run_id,
                lineage_token=lineage_token,
                loop_token=loop_token,
                join_token=join_token,
            )
            return

        worker = GitWorker(command=command, working_directory=cwd)
        self._active_workers[exec_id] = worker

        def on_output(line: str, _n=node, _e=exec_id, _r=run_id):
            if _r == self._run_id and self._running and _e in self._active_workers and _e not in self._retired_exec_ids:
                _n.append_output(line)
                if self.on_output_line:
                    self.on_output_line(_n, line)

        def on_finished(full: str, _n=node, _e=exec_id, _r=run_id,
                        _lt=lineage_token, _lp=loop_token, _jt=join_token, _action=action):
            result = ""
            if not full.strip():
                if _action == "git_add":
                    result = "git add: staged all changes."
                elif _action == "git_commit":
                    result = "git commit: committed successfully."
                elif _action == "git_push":
                    result = "git push: pushed successfully."
            self._on_invocation_done(
                _n,
                _e,
                result,
                error=False,
                run_id=_r,
                lineage_token=_lt,
                loop_token=_lp,
                join_token=_jt,
            )

        def on_error(msg: str, _n=node, _e=exec_id, _r=run_id,
                     _lt=lineage_token, _lp=loop_token, _jt=join_token):
            self._on_invocation_done(
                _n,
                _e,
                msg,
                error=True,
                run_id=_r,
                lineage_token=_lt,
                loop_token=_lp,
                join_token=_jt,
            )

        worker.output_line.connect(on_output)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    def _queue_child_triggers(self: "WorkflowCanvas", node: GraphNode, run_id: int,
                              branch: str = "output", lineage_token: str = "",
                              loop_token: str = "", join_token: str = "") -> int:
        """Queue deferred triggers for node's children. Returns the number of children queued."""
        from src.gui.loop_node import LoopNode
        if isinstance(node, (ConditionalNode, LoopNode)):
            # Only follow connections on the evaluated branch port
            edge_pairs = [
                (conn.source_node.node_id, conn.target_node.node_id, getattr(conn, "source_port", "output"))
                for conn in self._connections
                if conn.source_node is node and getattr(conn, "source_port", "output") == branch
            ]
        else:
            edge_pairs = [
                (conn.source_node.node_id, conn.target_node.node_id, getattr(conn, "source_port", "output"))
                for conn in self._connections
                if conn.source_node is node
            ]
        self._pending_child_triggers += len(edge_pairs)
        # Fan-out: each child gets a new unique lineage token; single child inherits same token.
        if len(edge_pairs) == 1:
            lineage_tokens = [lineage_token]
            join_tokens = [join_token]
        else:
            lineage_tokens = [str(uuid4()) for _ in edge_pairs]
            shared_join_token = lineage_token or join_token
            join_tokens = [shared_join_token for _ in edge_pairs]
        for (source_id, target_id, source_port), child_lt, child_jt in zip(
            edge_pairs, lineage_tokens, join_tokens
        ):
            QTimer.singleShot(
                0,
                lambda _src=source_id, _tgt=target_id, _run_id=run_id, _sp=source_port,
                       _lt=child_lt, _loop=loop_token, _jt=child_jt:
                    self._trigger_node_if_active(_src, _tgt, _run_id, _sp, _lt, _loop, _jt),
            )
        return len(edge_pairs)

    def _trigger_node_if_active(self: "WorkflowCanvas", source_id: str, target_id: str,
                                run_id: int, source_port: str = "output",
                                lineage_token: str = "", loop_token: str = "", join_token: str = ""):
        try:
            if run_id != self._run_id or not self._running or self._no_fanout:
                return
            edge_still_exists = any(
                conn.source_node.node_id == source_id
                and conn.target_node.node_id == target_id
                and getattr(conn, "source_port", "output") == source_port
                for conn in self._connections
            )
            if not edge_still_exists:
                return
            node = self._nodes.get(target_id)
            if node is None:
                return
            self._trigger_node(node, lineage_token, loop_token, join_token)
        finally:
            if run_id == self._run_id and self._pending_child_triggers > 0:
                self._pending_child_triggers -= 1
            self._check_drain()

    def _on_invocation_done(self: "WorkflowCanvas", node: GraphNode, exec_id: int,
                            result: str, error: bool, run_id: int = 0,
                            lineage_token: str = "", loop_token: str = "", join_token: str = ""):
        if exec_id not in self._active_workers:
            return
        streamed_output = self._exec_streamed_output.pop(exec_id, False)
        retired = exec_id in self._retired_exec_ids
        self._retired_exec_ids.discard(exec_id)
        del self._active_workers[exec_id]
        self._exec_node.pop(exec_id, None)
        self._exec_lineage.pop(exec_id, None)
        self._current_run_exec_ids.discard(exec_id)
        if run_id != self._run_id or not self._running:
            self._check_drain()
            return
        if retired:
            self._check_drain()
            return

        if error:
            msg = f"[Error] {result}"
            node.append_output(msg)
            if self.on_output_line:
                self.on_output_line(node, msg)
            node.set_status("error")
            if is_usage_limit_error(result):
                self.stop_all()
                QTimer.singleShot(
                    0,
                    lambda _nid=node.node_id, _msg=result:
                        self.usage_limit_hit.emit(_nid, _msg),
                )
        else:
            from src.gui.git_action_node import GitActionNode
            if isinstance(node, AttentionNode):
                node.clear_output()
                if self.on_output_cleared:
                    self.on_output_cleared(node)
                node.append_output(result)
                if self.on_output_line:
                    self.on_output_line(node, result)
            elif isinstance(node, FileOpNode):
                node.clear_output()
                if self.on_output_cleared:
                    self.on_output_cleared(node)
                node.append_output(result)
                if self.on_output_line:
                    self.on_output_line(node, result)
            elif isinstance(node, GitActionNode):
                if result:
                    node.append_output(result)
                    if self.on_output_line:
                        self.on_output_line(node, result)
            elif isinstance(node, LLMNode):
                if not streamed_output and result.strip():
                    for line in result.splitlines():
                        node.append_output(line)
                        if self.on_output_line:
                            self.on_output_line(node, line)
            else:
                node.output_text = result
            node.set_status("done")
            if not self._no_fanout:
                self._queue_child_triggers(node, run_id, lineage_token=lineage_token,
                                           loop_token=loop_token, join_token=join_token)

        self._check_drain()

    def _check_drain(self: "WorkflowCanvas"):
        if (
            self._running
            and not self._seeding_roots
            and not self._current_run_exec_ids
            and self._pending_child_triggers == 0
            and self._pending_join_waits == 0
        ):
            self._running = False
            self._loop_counters.clear()
            self._join_wait_counts.clear()
            for node in self._nodes.values():
                if node.status in {"running", "looping"}:
                    node.set_status("done")
            self.run_state_changed.emit(False)
            self.status_update.emit("Done.")
