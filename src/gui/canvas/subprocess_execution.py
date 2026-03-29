"""Subprocess-oriented canvas execution helpers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.gui.file_op_node import FileOpNode
from src.gui.script_runner.script_node import ALLOWED_SCRIPT_SUFFIXES, ScriptNode
from src.workers.git_worker import GitWorker
from src.workers.script_worker import ScriptWorker

if TYPE_CHECKING:
    from src.gui.canvas import WorkflowCanvas

_GIT_ACTION_TIMEOUT_SECONDS = 3600
_SCRIPT_TIMEOUT_SECONDS = 3600


class _SubprocessExecutionMixin:
    def _resolve_project_relative_path(
        self: "WorkflowCanvas",
        relative_path: str,
        *,
        empty_error: str,
    ) -> str:
        if not self._working_directory:
            raise ValueError("No project folder selected.")
        raw = relative_path.strip()
        if not raw:
            raise ValueError(empty_error)
        drive, _ = os.path.splitdrive(raw)
        if os.path.isabs(raw) or drive:
            raise ValueError("Path must be relative to the selected project folder.")
        project_root = os.path.realpath(self._working_directory)
        target = os.path.realpath(os.path.join(project_root, raw))
        try:
            common = os.path.commonpath([project_root, target])
        except ValueError as exc:
            raise ValueError("Path escapes the selected project folder.") from exc
        if os.path.normcase(common) != os.path.normcase(project_root):
            raise ValueError("Path escapes the selected project folder.")
        if os.path.normcase(target) == os.path.normcase(project_root):
            raise ValueError("Path must point to a file inside the project folder.")
        return target

    def _resolve_file_op_path(self: "WorkflowCanvas", filename: str) -> str:
        return self._resolve_project_relative_path(filename, empty_error="Filename is empty.")

    def _resolve_script_path(self: "WorkflowCanvas", script_path: str) -> str:
        target = self._resolve_project_relative_path(script_path, empty_error="Script path is empty.")
        suffix = os.path.splitext(target)[1].lower()
        if suffix not in ALLOWED_SCRIPT_SUFFIXES:
            raise ValueError("Script path must end in .bat, .cmd, or .ps1.")
        if not os.path.isfile(target):
            raise ValueError(f"Script file not found: {target}")
        return target

    def _build_script_command(self, script_path: str) -> list[str]:
        suffix = os.path.splitext(script_path)[1].lower()
        if suffix in {".bat", ".cmd"}:
            return ["cmd.exe", "/c", script_path]
        if suffix == ".ps1":
            return [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_path,
            ]
        raise ValueError(f"Unsupported script type: {suffix or '(none)'}")

    def _fire_file_op(
        self: "WorkflowCanvas",
        node: FileOpNode,
        exec_id: int,
        lineage_token: str = "",
        loop_token: str = "",
        join_token: str = "",
    ):
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

    def _fire_git_action(
        self: "WorkflowCanvas",
        node,
        exec_id: int,
        lineage_token: str = "",
        loop_token: str = "",
        join_token: str = "",
    ):
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

        worker = GitWorker(
            command=command,
            working_directory=cwd,
            timeout=_GIT_ACTION_TIMEOUT_SECONDS,
        )
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

    def _fire_script_node(
        self: "WorkflowCanvas",
        node: ScriptNode,
        exec_id: int,
        lineage_token: str = "",
        loop_token: str = "",
        join_token: str = "",
    ):
        run_id = self._run_id
        try:
            script_path = self._resolve_script_path(node.script_path)
            command = self._build_script_command(script_path)
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

        worker = ScriptWorker(
            command=command,
            working_directory=self._working_directory,
            timeout=_SCRIPT_TIMEOUT_SECONDS,
            stdin_text="\n" if node.auto_send_enter else "",
        )
        self._active_workers[exec_id] = worker

        def on_output(line: str, _n=node, _e=exec_id, _r=run_id):
            if _r == self._run_id and self._running and _e in self._active_workers and _e not in self._retired_exec_ids:
                _n.append_output(line)
                if self.on_output_line:
                    self.on_output_line(_n, line)

        def on_finished(full: str, _n=node, _e=exec_id, _r=run_id,
                        _lt=lineage_token, _lp=loop_token, _jt=join_token, _path=node.script_path):
            result = full if full.strip() else f"Script completed: {_path}"
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
