# workers Developer Guide

## Purpose
Hosts threaded execution logic so long-running subprocess calls do not block the Qt event loop.

## Contents
- `llm_worker.py`: `QThread` wrapper that starts provider subprocesses, streams line output, enforces timeout, supports cancellation, and returns captured session IDs for structured-output providers.
- `git_worker.py`: `QThread` wrapper that runs git commands in the background with timeout and cancellation support.
- `script_worker.py`: `QThread` wrapper that runs `.bat`, `.cmd`, or `.ps1` launch commands in the background with timeout and cancellation support.

## Key Behavior
- `LLMWorker` receives a `BaseLLMProvider`, prompt text, model id, optional session id, optional working directory, and timeout. It runs the provider command, writes prompt text to stdin only when the provider says it uses stdin, merges stdout and stderr, and emits lines through `output_line` for plain-text providers.
- `GitWorker` receives a concrete git command, optional working directory, and timeout; validates cwd exists before launch; merges stdout and stderr and emits lines through `output_line`.
- `ScriptWorker` receives a fully built script command, optional working directory, timeout, and optional `stdin_text`; validates cwd exists before launch; writes `stdin_text` once after spawn when provided; then merges stdout and stderr and emits lines through `output_line`.
- `LLMWorker.finished` and `LLMWorker.error` both emit `(output_text, session_id)`.
- For Claude and Codex providers, the worker does not stream raw JSON lines to the node output. It parses structured output, extracts the final assistant text, and captures `session_id` for workflow persistence.
- For non-structured providers such as Gemini, the worker still streams plain text line by line.

## Cancellation Contract
- `cancel()` is non-blocking. It sets `_cancelled` and spawns a daemon watchdog thread that runs terminate, wait up to 4 seconds, then kill if needed.
- The worker always emits a terminal cancelled error path on every cancellation window, including before spawn and immediately after spawn.
- The canvas ignores cancelled callbacks as real failures through three guards: active-worker membership, current-run matching, and retired-exec suppression.
- `GitWorker` uses the same termination contract so `WorkflowCanvas.stop_all()` can cancel in-flight git operations without freezing the UI.

## When To Edit
- Timeout or cancellation semantics: `llm_worker.py`.
- CLI invocation behavior or prompt-transport handling: `llm_worker.py` plus provider files in `src/llm/`.
- Git subprocess execution and cancellation behavior: `git_worker.py`.
- Script subprocess execution and cancellation behavior: `script_worker.py`.
