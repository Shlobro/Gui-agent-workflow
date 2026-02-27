"""_ExecutionMixin — workflow run/stop logic for WorkflowCanvas."""

import os
from collections import deque
from typing import TYPE_CHECKING, List, Sequence

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from src.workers.llm_worker import LLMWorker
from src.gui.file_op_node import FileOpNode
from src.gui.llm_node import StartNode, WorkflowNode
from src.gui.workflow_io import get_provider_for_model

if TYPE_CHECKING:
    from src.gui.canvas import WorkflowCanvas

GraphNode = WorkflowNode


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
            "Use File → Open Project Folder… to choose one.",
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
        for worker in list(self._active_workers.values()):
            if worker is not None:
                worker.cancel()
        for node in self._nodes.values():
            if node.status == "running":
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

    def _source_has_outgoing(self: "WorkflowCanvas", source) -> bool:
        return any(conn.source_node is source for conn in self._connections)

    def _validate_nodes(self: "WorkflowCanvas", nodes: Sequence[GraphNode]) -> List[str]:
        errors = []
        for node in nodes:
            title = getattr(node, "title", node.node_id)
            if isinstance(node, FileOpNode):
                if not node.filename.strip():
                    errors.append(f'\u2022 "{title}" has no filename set.')
            else:
                if not node.prompt_text.strip():
                    errors.append(f'\u2022 "{title}" has no prompt.')
                if not node.model_id:
                    errors.append(f'\u2022 "{title}" has no model selected.')
                elif get_provider_for_model(node.model_id) is None:
                    errors.append(f'\u2022 "{title}" has unknown model "{node.model_id}".')
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
            for node in roots:
                self._trigger_node(node)
        finally:
            self._seeding_roots = False
        self._check_drain()

    def _trigger_node(self: "WorkflowCanvas", node: GraphNode):
        if not self._running:
            return
        self._exec_counter += 1
        self._fire_invocation(node, self._exec_counter)

    def _fire_invocation(self: "WorkflowCanvas", node: GraphNode, exec_id: int):
        self._active_workers[exec_id] = None
        self._exec_node[exec_id] = node.node_id
        self._current_run_exec_ids.add(exec_id)
        node.set_status("running")
        if isinstance(node, FileOpNode):
            self._fire_file_op(node, exec_id)
            return
        model_id = node.model_id
        if not model_id:
            node.append_output("[Error] No model selected.")
            if self.on_output_line:
                self.on_output_line(node, "[Error] No model selected.")
            node.set_status("error")
            del self._active_workers[exec_id]
            self._exec_node.pop(exec_id, None)
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
            self._current_run_exec_ids.discard(exec_id)
            return

        worker = LLMWorker(provider, node.prompt_text, model=model_id,
                           working_directory=self._working_directory)
        self._active_workers[exec_id] = worker
        run_id = self._run_id

        def on_output(line: str, _n=node, _e=exec_id, _r=run_id):
            if _r == self._run_id and self._running and _e in self._active_workers and _e not in self._retired_exec_ids:
                _n.append_output(line)
                if self.on_output_line:
                    self.on_output_line(_n, line)

        def on_finished(full: str, _n=node, _e=exec_id, _r=run_id):
            self._on_invocation_done(_n, _e, full, error=False, run_id=_r)

        def on_error(msg: str, _n=node, _e=exec_id, _r=run_id):
            self._on_invocation_done(_n, _e, msg, error=True, run_id=_r)

        worker.output_line.connect(on_output)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

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

    def _fire_file_op(self: "WorkflowCanvas", node: FileOpNode, exec_id: int):
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
            self._on_invocation_done(node, exec_id, result, error=False, run_id=run_id)
        except Exception as exc:
            self._on_invocation_done(node, exec_id, str(exc), error=True, run_id=run_id)

    def _queue_child_triggers(self: "WorkflowCanvas", node: GraphNode, run_id: int):
        edge_pairs = [
            (conn.source_node.node_id, conn.target_node.node_id)
            for conn in self._connections
            if conn.source_node is node
        ]
        self._pending_child_triggers += len(edge_pairs)
        for source_id, target_id in edge_pairs:
            QTimer.singleShot(
                0,
                lambda _src=source_id, _tgt=target_id, _run_id=run_id: self._trigger_node_if_active(_src, _tgt, _run_id),
            )

    def _trigger_node_if_active(self: "WorkflowCanvas", source_id: str, target_id: str, run_id: int):
        try:
            if run_id != self._run_id or not self._running or self._no_fanout:
                return
            edge_still_exists = any(
                conn.source_node.node_id == source_id and conn.target_node.node_id == target_id
                for conn in self._connections
            )
            if not edge_still_exists:
                return
            node = self._nodes.get(target_id)
            if node is None:
                return
            self._trigger_node(node)
        finally:
            if run_id == self._run_id and self._pending_child_triggers > 0:
                self._pending_child_triggers -= 1
            self._check_drain()

    def _on_invocation_done(self: "WorkflowCanvas", node: GraphNode, exec_id: int,
                            result: str, error: bool, run_id: int = 0):
        if exec_id not in self._active_workers:
            return
        retired = exec_id in self._retired_exec_ids
        self._retired_exec_ids.discard(exec_id)
        del self._active_workers[exec_id]
        self._exec_node.pop(exec_id, None)
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
        else:
            if isinstance(node, FileOpNode):
                node.clear_output()
                if self.on_output_cleared:
                    self.on_output_cleared(node)
                node.append_output(result)
                if self.on_output_line:
                    self.on_output_line(node, result)
            else:
                node.output_text = result
            node.set_status("done")
            if not self._no_fanout:
                self._queue_child_triggers(node, run_id)

        self._check_drain()

    def _check_drain(self: "WorkflowCanvas"):
        if (
            self._running
            and not self._seeding_roots
            and not self._current_run_exec_ids
            and self._pending_child_triggers == 0
        ):
            self._running = False
            self.run_state_changed.emit(False)
            self.status_update.emit("Done.")
