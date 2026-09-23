"""Qt workflow engine adapter for the Electron editor."""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

import src.llm  # noqa: F401
from src.gui.canvas import WorkflowCanvas
from src.gui.llm_node import LLMNode
from src.gui.workflow_io import get_provider_for_model
from src.llm.base_provider import LLMProviderRegistry
from src.llm.cli_detection import detect_installed_clis, is_provider_installed
from src.llm.profiles import discover_profiles
from src.platform_power import allow_sleep, prevent_sleep
from src.llm.prompt_injection import (
    PromptInjectionConfig,
    PromptInjectionStore,
    PromptTemplate,
    derive_node_template_overrides,
    normalize_placement,
)

PREFIX = "@@GUI@@"
NODE_LABELS = {
    "llm": "LLM",
    "create_file": "File Op",
    "truncate_file": "File Op",
    "delete_file": "File Op",
    "conditional": "Condition",
    "loop": "Loop",
    "join": "Join",
    "git_action": "Git",
    "script_runner": "Script",
    "attention": "Attention",
    "variable": "Variable",
}


def send(message: dict) -> None:
    sys.stdout.write(
        PREFIX + json.dumps(message, ensure_ascii=False, default=str) + "\n"
    )
    sys.stdout.flush()


def read_requests(inbox: queue.Queue) -> None:
    for line in sys.stdin:
        try:
            inbox.put(json.loads(line))
        except json.JSONDecodeError:
            continue
    inbox.put({"action": "quit"})


class DesktopBridge:
    def __init__(self, app: QApplication):
        self.app = app
        self.canvas = WorkflowCanvas()
        self.prompt_store = PromptInjectionStore()
        self.prompt_config = self.prompt_store.load()
        self.model_catalog = self._models()
        self.canvas.set_prompt_injections(
            self.prompt_config, self.prompt_config.default_enabled_template_ids
        )
        self.inbox: queue.Queue = queue.Queue()
        self.project_folder = ""
        self.workflow_path = ""
        self.dirty = False
        self.status = "Ready"
        self.last_state = ""
        self.saved_sessions_pending = False
        self.one_off_text = ""
        self.one_off_placement = "append"
        self.one_off_active = False
        self.attention_waits: dict[str, tuple[QEventLoop, list[bool]]] = {}
        self.scheduled_resume: tuple[str, float] | None = None
        self.resume_timer = QTimer()
        self.resume_timer.setSingleShot(True)
        self.resume_timer.timeout.connect(self._fire_scheduled_resume)
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.canvas.status_update.connect(self._set_status)
        self.canvas.usage_limit_hit.connect(self._usage_limit)
        self.canvas.run_state_changed.connect(self._run_state_changed)
        self.canvas.on_attention_requested = self._attention
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(160)
        threading.Thread(target=read_requests, args=(self.inbox,), daemon=True).start()
        self.publish(force=True)

    def _set_status(self, value: str) -> None:
        self.status = value

    def _usage_limit(self, node_id: str, error: str) -> None:
        send({"type": "usage_limit", "node_id": node_id, "error": error})

    def _attention(self, node, message: str) -> bool:
        token = str(uuid4())
        loop = QEventLoop()
        answer = [False]
        self.attention_waits[token] = (loop, answer)
        send(
            {
                "type": "attention",
                "token": token,
                "node_id": node.node_id,
                "title": node.title,
                "message": message,
            }
        )
        poll = QTimer()
        poll.timeout.connect(self.tick)
        poll.start(80)
        try:
            loop.exec()
        finally:
            poll.stop()
        self.attention_waits.pop(token, None)
        return answer[0]

    def _run_state_changed(self, running: bool) -> None:
        if running:
            prevent_sleep()
        else:
            allow_sleep()
        if not running and self.one_off_active:
            self.one_off_active = False
            self.one_off_text = ""
            self._apply_prompt_options()

    def _fire_scheduled_resume(self) -> None:
        pending = self.scheduled_resume
        self.scheduled_resume = None
        if (
            pending is None
            or self.canvas._running
            or pending[0] not in self.canvas._nodes
        ):
            return
        try:
            self._run({"mode": "from", "ids": [pending[0]]})
        except ValueError as exc:
            self.status = f"Scheduled resume failed: {exc}"

    def _apply_prompt_options(self) -> None:
        self.canvas.set_prompt_injections(
            self.prompt_config,
            self.prompt_config.default_enabled_template_ids,
            self.one_off_text,
            self.one_off_placement,
        )

    def _models(self) -> list[dict]:
        result = []
        for provider in LLMProviderRegistry.all():
            models = []
            for entry in provider.get_model_entries():
                models.append(
                    {
                        "id": entry.model_id,
                        "label": entry.label,
                        "variants": [asdict(variant) for variant in entry.variants],
                        "default_variant": entry.default_variant_id,
                    }
                )
            result.append(
                {
                    "name": provider.name,
                    "label": provider.display_name,
                    "installed": is_provider_installed(provider),
                    "models": models,
                    "profiles": [
                        profile.name for profile in discover_profiles(provider.name)
                    ],
                }
            )
        return result

    def state(self) -> dict:
        workflow = self.canvas.get_workflow_data()
        nodes = []
        for node in self.canvas._nodes.values():
            record = node.to_dict()
            record.update(
                {
                    "node_type": record.get("node_type", "llm"),
                    "status": node.status,
                    "invalid": bool(node.is_invalid),
                    "validation": self.canvas._node_validation_errors(node),
                    "output": node.output_text,
                }
            )
            if isinstance(node, LLMNode):
                record["conversations"] = [
                    {
                        "id": conversation.conversation_id,
                        "session_id": conversation.session_id,
                        "items": [asdict(item) for item in conversation.items],
                    }
                    for conversation in node.conversations.items
                ]
                record["preview"] = self.canvas.render_llm_prompt_text(node)
                provider = get_provider_for_model(node.model_id or "")
                record["available_named_sessions"] = [
                    name
                    for name, _label in self.canvas.available_named_session_options_for_node(
                        node.node_id, provider.name if provider else ""
                    )
                    if self.canvas.named_session_record(name).get("session_id")
                ]
            nodes.append(record)
        return {
            "nodes": nodes,
            "connections": workflow["connections"],
            "start_pos": workflow["start_pos"],
            "named_sessions": workflow["named_sessions"],
            "project_folder": self.project_folder,
            "workflow_path": self.workflow_path,
            "dirty": self.dirty,
            "running": self.canvas._running,
            "status": self.status,
            "models": self.model_catalog,
            "templates": [
                asdict(template) for template in self.prompt_config.templates
            ],
            "default_template_ids": list(
                self.prompt_config.default_enabled_template_ids
            ),
            "one_off_text": self.one_off_text,
            "one_off_placement": self.one_off_placement,
            "saved_sessions_pending": self.saved_sessions_pending,
            "scheduled_resume": self.scheduled_resume,
            "can_undo": bool(self.undo_stack),
            "can_redo": bool(self.redo_stack),
        }

    def publish(self, force: bool = False) -> None:
        state = self.state()
        encoded = json.dumps(state, ensure_ascii=False, default=str)
        if force or encoded != self.last_state:
            self.last_state = encoded
            send({"type": "state", "state": state})

    def _remember(self) -> None:
        if self.canvas._running:
            raise ValueError("Stop the workflow before editing its graph.")
        self.undo_stack.append(self.canvas.get_workflow_data())
        self.undo_stack = self.undo_stack[-100:]
        self.redo_stack.clear()
        self.dirty = True

    def _node(self, node_id: str):
        node = self.canvas._nodes.get(node_id)
        if node is None:
            raise ValueError("Node no longer exists.")
        return node

    def _add_node(self, payload: dict) -> str:
        node_type = payload.get("node_type", "llm")
        if node_type not in NODE_LABELS:
            raise ValueError("Unknown node type.")
        self._remember()
        self.canvas._node_counter += 1
        index = self.canvas._node_counter
        data = {
            "id": str(uuid4()),
            "label_index": index,
            "x": float(payload.get("x", 0)),
            "y": float(payload.get("y", 0)),
            "name": f"{NODE_LABELS[node_type]} {index}",
        }
        if node_type == "llm":
            data.update(
                {"model": self.canvas._resolve_default_llm_model_id(), "prompt": ""}
            )
        else:
            data["node_type"] = node_type
        node = self.canvas._undo_add_node(data, index)
        return node.node_id

    def _patch_node(self, payload: dict) -> None:
        node = self._node(payload["id"])
        patch = payload.get("patch", {})
        allowed = set(node.to_dict()) - {
            "id",
            "label_index",
            "saved_session_id",
            "saved_session_provider",
        }
        if not isinstance(patch, dict) or not set(patch).issubset(allowed):
            raise ValueError("Invalid node fields.")
        self._remember()
        data = node.to_dict()
        data.update(patch)
        if (
            isinstance(node, LLMNode)
            and "model" in patch
            and patch["model"] != node.model_id
        ):
            data["saved_session_id"] = ""
            data["saved_session_provider"] = ""
        node.from_dict(data)
        self.canvas.reconcile_named_sessions()
        self.canvas.refresh_node_validation_state()

    def _connect(self, payload: dict) -> None:
        source_id = payload.get("from")
        target_id = payload.get("to")
        port = payload.get("source_port", "output")
        source = (
            self.canvas._start_node if source_id == "start" else self._node(source_id)
        )
        target = self._node(target_id)
        source_type = (
            "start"
            if source_id == "start"
            else source.to_dict().get("node_type", "llm")
        )
        valid_ports = {"conditional": {"true", "false"}, "loop": {"loop", "done"}}
        if port not in valid_ports.get(source_type, {"output"}):
            raise ValueError("Invalid output port.")
        if source is target:
            raise ValueError("A node cannot connect directly to itself.")
        target_type = target.to_dict().get("node_type", "llm")
        loop_feedback = (
            source_type == "loop" and port == "loop"
        ) or target_type == "loop"
        if (
            self.canvas._would_create_cycle(source, target)
            and not loop_feedback
            and not payload.get("confirmed_cycle")
        ):
            raise ValueError(
                "Cycle warning: these nodes will keep running until stopped. Confirm to connect them."
            )
        if self.canvas._find_connection(source_id, target_id, port):
            return
        self._remember()
        self.canvas._undo_add_connection(source, target, port)
        self.canvas.refresh_node_validation_state()

    def _run(self, payload: dict) -> None:
        if self.canvas._running:
            raise ValueError("A workflow is already running.")
        if not self.project_folder:
            raise ValueError("Choose a project folder before running.")
        self.resume_timer.stop()
        self.scheduled_resume = None
        if self.saved_sessions_pending:
            choice = payload.get("session_choice")
            if choice not in {"resume", "fresh"}:
                raise ValueError(
                    "Choose whether to resume saved sessions or start fresh."
                )
            if choice == "fresh":
                self.canvas.clear_all_llm_sessions()
            self.saved_sessions_pending = False
        mode = payload.get("mode", "all")
        ids = payload.get("ids", [])
        if mode == "all":
            reachable = self.canvas._reachable_from(self.canvas._start_node)
            nodes = [node for node in reachable if node is not self.canvas._start_node]
            roots = self.canvas._direct_children(self.canvas._start_node)
            no_fanout = False
        elif mode == "selected":
            roots = [self._node(node_id) for node_id in ids]
            nodes = roots
            no_fanout = True
        elif mode == "from" and len(ids) == 1:
            roots = [self._node(ids[0])]
            nodes = self.canvas._reachable_from(roots[0])
            no_fanout = False
        else:
            raise ValueError("Choose a node to run.")
        if not nodes:
            raise ValueError("Connect a node to Start first.")
        errors = self.canvas._validate_nodes(nodes)
        if errors:
            raise ValueError("\n".join(errors))
        self.one_off_active = bool(self.one_off_text)
        if any(isinstance(node, LLMNode) for node in nodes):
            self.dirty = True
        self.canvas._run_workflow(nodes, roots=roots, no_fanout=no_fanout)

    def dispatch(self, action: str, payload: dict):
        if action == "state":
            return self.state()
        if action == "quit":
            self.canvas.stop_all()
            self.app.quit()
            return None
        if action == "project":
            if self.canvas._running:
                raise ValueError("Stop the workflow before changing project folders.")
            folder = Path(payload["path"]).expanduser().resolve()
            if not folder.is_dir():
                raise ValueError("Project folder does not exist.")
            self.project_folder = str(folder)
            self.canvas.set_working_directory(self.project_folder)
            return None
        if action == "load":
            if self.canvas._running:
                raise ValueError("Stop the workflow before opening another file.")
            path = Path(payload["path"]).expanduser().resolve()
            data = json.loads(path.read_text(encoding="utf-8"))
            self.canvas.load_workflow_data(data)
            self.workflow_path = str(path)
            self.status = "Workflow loaded."
            self.dirty = False
            self.saved_sessions_pending = self.canvas.has_saved_llm_sessions()
            self.undo_stack.clear()
            self.redo_stack.clear()
            return None
        if action == "save":
            path = Path(payload["path"]).expanduser().resolve()
            path.write_text(
                json.dumps(self.canvas.get_workflow_data(), indent=2), encoding="utf-8"
            )
            self.workflow_path = str(path)
            self.dirty = False
            return None
        if action == "add_node":
            return self._add_node(payload)
        if action == "patch_node":
            return self._patch_node(payload)
        if action == "move_node":
            self._remember()
            node = (
                self.canvas._start_node
                if payload["id"] == "start"
                else self._node(payload["id"])
            )
            node.setPos(float(payload["x"]), float(payload["y"]))
            return None
        if action == "connect":
            return self._connect(payload)
        if action == "delete_node":
            self._remember()
            self.canvas._undo_remove_node(payload["id"])
            return None
        if action == "copy":
            self.canvas._scene.clearSelection()
            for node_id in payload.get("ids", []):
                node = self.canvas._nodes.get(node_id)
                if node is not None:
                    node.setSelected(True)
            self.canvas._copy_selected()
            return None
        if action == "paste":
            if self.canvas._clipboard:
                self._remember()
                self.canvas._paste()
            return None
        if action == "delete_connection":
            conn = self.canvas._find_connection(
                payload["from"], payload["to"], payload.get("source_port", "output")
            )
            if conn:
                self._remember()
                self.canvas._undo_remove_connection_item(conn)
            return None
        if action == "set_vertices":
            conn = self.canvas._find_connection(
                payload["from"], payload["to"], payload.get("source_port", "output")
            )
            if conn is None:
                raise ValueError("Connection no longer exists.")
            points = payload.get("vertices", [])
            if not isinstance(points, list) or any(
                not isinstance(point, list)
                or len(point) != 2
                or not all(isinstance(value, (int, float)) for value in point)
                for point in points
            ):
                raise ValueError("Invalid bend points.")
            self._remember()
            conn.set_manual_points_from_tuples(
                [(float(x), float(y)) for x, y in points]
            )
            return None
        if action == "clear":
            self._remember()
            self.canvas.clear_canvas()
            self.workflow_path = ""
            self.saved_sessions_pending = False
            self.status = "Canvas cleared."
            return None
        if action == "undo" and self.undo_stack:
            if self.canvas._running:
                raise ValueError("Stop the workflow before undoing edits.")
            self.redo_stack.append(self.canvas.get_workflow_data())
            self.canvas.load_workflow_data(self.undo_stack.pop())
            self.dirty = True
            return None
        if action == "redo" and self.redo_stack:
            if self.canvas._running:
                raise ValueError("Stop the workflow before redoing edits.")
            self.undo_stack.append(self.canvas.get_workflow_data())
            self.canvas.load_workflow_data(self.redo_stack.pop())
            self.dirty = True
            return None
        if action == "run":
            return self._run(payload)
        if action == "stop":
            self.canvas.stop_all()
            for loop, answer in self.attention_waits.values():
                answer[0] = False
                loop.quit()
            return None
        if action == "schedule_resume":
            node_id = str(payload.get("id", ""))
            self._node(node_id)
            timestamp = float(payload.get("at", 0)) / 1000
            delay_ms = max(1, int((timestamp - time.time()) * 1000))
            if delay_ms > 2_147_483_647:
                raise ValueError("Scheduled time is too far away.")
            self.scheduled_resume = (node_id, timestamp)
            self.resume_timer.start(delay_ms)
            self.status = "Auto-resume scheduled."
            return None
        if action == "clear_sessions":
            if self.canvas._running:
                raise ValueError("Stop the workflow before clearing sessions.")
            self.canvas.clear_all_llm_sessions()
            self.saved_sessions_pending = False
            self.dirty = True
            return None
        if action == "rescan_models":
            detect_installed_clis(force=True)
            self.model_catalog = self._models()
            self.canvas.refresh_node_validation_state()
            return None
        if action == "templates":
            if self.canvas._running:
                raise ValueError("Stop the workflow before editing prompt templates.")
            records = payload.get("templates", [])
            defaults = payload.get("default_template_ids", [])
            if not isinstance(records, list) or not isinstance(defaults, list):
                raise ValueError("Invalid template settings.")
            templates = tuple(
                PromptTemplate(
                    template_id=str(record.get("template_id") or uuid4()),
                    name=str(record.get("name", "")),
                    content=str(record.get("content", "")),
                    built_in=bool(record.get("built_in", False)),
                    placement=normalize_placement(record.get("placement", "append")),
                )
                for record in records
                if isinstance(record, dict)
            )
            self.prompt_store.save(PromptInjectionConfig(templates, tuple(defaults)))
            self.prompt_config = self.prompt_store.load()
            self._apply_prompt_options()
            return None
        if action == "one_off":
            if self.canvas._running:
                raise ValueError("Stop the workflow before changing next-run context.")
            self.one_off_text = str(payload.get("text", ""))[:4000]
            self.one_off_placement = normalize_placement(
                payload.get("placement", "append")
            )
            self._apply_prompt_options()
            return None
        if action == "node_templates":
            node = self._node(payload["id"])
            if not isinstance(node, LLMNode):
                raise ValueError("Template selection requires an LLM node.")
            side = payload.get("side")
            if side not in {"prepend", "append"}:
                raise ValueError("Invalid template side.")
            self._remember()
            local, disabled = derive_node_template_overrides(
                self.prompt_config,
                self.prompt_config.default_enabled_template_ids,
                payload.get("ids", []),
            )
            setattr(node, f"{side}_template_ids", local)
            setattr(node, f"{side}_disabled_global_template_ids", disabled)
            return None
        if action == "attention_response":
            pending = self.attention_waits.get(payload.get("token"))
            if pending:
                loop, answer = pending
                answer[0] = bool(payload.get("continue"))
                loop.quit()
            return None
        raise ValueError(f"Unknown action: {action}")

    def tick(self) -> None:
        while True:
            try:
                request = self.inbox.get_nowait()
            except queue.Empty:
                break
            request_id = request.get("id")
            try:
                result = self.dispatch(
                    request.get("action", ""), request.get("payload") or {}
                )
                if request_id is not None:
                    send({"id": request_id, "ok": True, "result": result})
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                if request_id is not None:
                    send({"id": request_id, "ok": False, "error": str(exc)})
        self.publish()


def main() -> int:
    # The Electron host reads and writes UTF-8; Windows defaults pipes to cp1252.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    app = QApplication(sys.argv)
    app.setApplicationName("LLM Workflow Runtime")
    bridge = DesktopBridge(app)
    app.bridge = bridge
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
