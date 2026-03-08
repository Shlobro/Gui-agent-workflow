# workers Developer Guide

## Purpose
Hosts threaded execution logic so long-running subprocess calls do not block the Qt event loop.

## Contents
- `llm_worker.py`: `QThread` wrapper that starts provider subprocesses, streams line output, enforces timeout, and supports cancellation.
- `git_worker.py`: `QThread` wrapper that runs git commands (`git add`, `git commit`, `git push`) in the background with timeout/cancellation support and merged stdout/stderr capture.
- `__init__.py`: Package marker.

## Key Behavior
- `LLMWorker` behavior: receives a `BaseLLMProvider`, prompt text, model id, optional working directory, and timeout; runs the provider command; writes prompt text to subprocess stdin; merges stdout/stderr and emits lines through `output_line`. On non-zero exit, `error` is emitted with the full accumulated output as the payload (so callers can inspect the text for usage/rate-limit patterns); zero-exit emits `finished`.
- `GitWorker` behavior: receives a concrete git command (for example `["git", "commit", "-m", "..."]`), optional working directory, and timeout; validates cwd exists before launch; merges stdout/stderr and emits lines through `output_line`.
- Completion emits `finished(full_output)`; failures emit `error(message)`. For `GitWorker` non-zero exits, the error payload is a concise summary (`git command failed (exit X)`) because detailed command output is already streamed line-by-line through `output_line`. If cwd is invalid, `GitWorker` emits `Working directory not found: ...`; missing commands emit `Command not found: ...`.
- Cancellation: `cancel()` is non-blocking — it sets a flag and spawns a daemon watchdog thread that runs terminate→wait(4s)→kill, guaranteeing the subprocess dies and the pipe closes even if the worker thread is blocked in `readline()`. The worker thread always emits `error("Cancelled")` on every cancelled exit path, guaranteeing a terminal signal. The canvas ignores cancelled callbacks as real failures; three guards filter unwanted mutations: (1) `_active_workers` membership is the double-call gate in `_on_invocation_done`; (2) `run_id`/`_running` skip terminal callbacks from a previous run; (3) `_retired_exec_ids` suppresses both streamed output (`on_output`) and terminal node mutation for exec_ids whose node was deleted mid-run — those callbacks still clean up refs and call `_check_drain()`.
- `GitWorker` uses the same cancellation contract (`cancel()` terminate→wait→kill) so `WorkflowCanvas.stop_all()` can cancel in-flight git operations (for example, long `git push`) without freezing the UI. Timeout is enforced by an internal watchdog that terminates the subprocess when the deadline expires, so silent/hung commands do not bypass timeout while `readline()` is waiting.

## When To Edit
- Timeout/cancellation semantics: `llm_worker.py`.
- CLI invocation behavior or cwd handling: `llm_worker.py` plus provider files in `src/llm/`.
- Git subprocess execution and cancellation behavior: `git_worker.py`.
