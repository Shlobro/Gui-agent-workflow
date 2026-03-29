# script_runner Developer Guide

## Purpose
`src/gui/script_runner/` contains the workflow node type that executes a selected Windows script file from the active project folder.

## Contents
- `script_node.py`: Compact `ScriptNode` graphics item plus serialization constants and the factory used by canvas load/paste flows.
- `__init__.py`: Re-exports `ScriptNode`.

## Behavior
- `ScriptNode` is a single-input, single-output compact node like other utility nodes.
- The editable payload is `script_path`, stored as a project-relative path in workflow JSON.
- `auto_send_enter` is an optional boolean that writes one newline to the script's stdin immediately after launch, then closes stdin. This is intended for scripts that pause once for Enter.
- Supported script extensions are `.bat`, `.cmd`, and `.ps1`.
- Execution is handled by `ScriptWorker` in `src/workers/script_worker.py`; the node class only owns UI state, rendering, and serialization.

## When To Edit
- Change script-node rendering or serialized fields: `script_node.py`.
- Change execution or process-launch semantics: `src/workers/script_worker.py` and `src/gui/canvas/subprocess_execution.py`.
