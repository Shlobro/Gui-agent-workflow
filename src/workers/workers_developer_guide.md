# workers Developer Guide

## Purpose
Hosts threaded execution logic so long-running subprocess calls do not block the Qt event loop.

## Contents
- `llm_worker.py`: `QThread` wrapper that starts provider subprocesses, streams line output, enforces timeout, supports cancellation, and returns captured session IDs for structured-output providers.
- `git_worker.py`: `QThread` wrapper that runs git commands in the background with timeout and cancellation support.
- `script_worker.py`: `QThread` wrapper that runs `.bat`, `.cmd`, or `.ps1` launch commands in the background with timeout and cancellation support.
- `process_tree.py`: `terminate_tree` (blocking) and `terminate_tree_async` (daemon thread) stop a subprocess together with its descendants. All workers use it for cancellation and timeouts.

## Key Behavior
- `LLMWorker` receives a `BaseLLMProvider`, prompt text, model id, optional session id, optional working directory, optional `env_overlay`, and timeout. It runs the provider command, writes prompt text to stdin only when the provider says it uses stdin, merges stdout and stderr, and emits lines through `output_line` for plain-text providers. When `env_overlay` is non-empty it is merged onto a copy of `os.environ` for the subprocess; this is how account-profile selection (e.g. `CODEX_HOME`, `CLAUDE_CONFIG_DIR`) reaches the CLI.
- For structured-output providers, `LLMWorker` accumulates every raw line for final parsing and emits each line's `StreamEvent`s (from the provider's `structured_output_events`) through `stream_event` while the subprocess is running, so tool calls and intermediate replies appear in the chat transcript live.
- `GitWorker` receives a concrete git command, optional working directory, and timeout; validates cwd exists before launch; merges stdout and stderr and emits lines through `output_line`.
- `ScriptWorker` receives a fully built script command, optional working directory, timeout, and optional `stdin_text`; validates cwd exists before launch; writes `stdin_text` once after spawn when provided; then merges stdout and stderr and emits lines through `output_line`.
- `LLMWorker.finished` and `LLMWorker.error` both emit `(output_text, session_id)`.
- For structured-output providers (Claude, Codex, Grok, OpenCode), the worker does not stream raw JSON lines to the node output. It parses structured output, extracts the final assistant text, captures the session id for workflow persistence, and emits provider-mapped `StreamEvent`s during execution. Grok produces no live events in `json` mode; its result arrives as one final parse.
- Workers emit `finished`/`error` from inside `run()`. Receivers must keep a reference until the thread has exited (the canvas waits on the thread in `_drop_exec`); destroying a running `QThread` aborts the process.
- For non-structured providers, if any exist, the worker streams plain text line by line. All current built-in providers are structured-output providers.

## Cancellation Contract
- `cancel()` is non-blocking. It sets `_cancelled` and calls `terminate_tree_async`.
- On Windows, `terminate_tree` runs `taskkill /T /F` so the whole tree dies. Workers launch CLIs through `cmd` or `powershell` shims, and `Popen.terminate` alone would end only the shim. That would leave the real tool running and the stdout pipe open, so the worker thread would never return from `readline()`. On other platforms it runs terminate, waits up to 4 seconds, then kills.
- The worker always emits a terminal cancelled error path on every cancellation window, including before spawn and immediately after spawn.
- The canvas ignores cancelled callbacks as real failures through three guards: active-worker membership, current-run matching, and retired-exec suppression.
- `GitWorker` uses the same termination contract so `WorkflowCanvas.stop_all()` can cancel in-flight git operations without freezing the UI.

## When To Edit
- Timeout or cancellation semantics: `llm_worker.py`; process termination itself: `process_tree.py`.
- CLI invocation behavior or prompt-transport handling: `llm_worker.py` plus provider files in `src/llm/`.
- Git subprocess execution and cancellation behavior: `git_worker.py`.
- Script subprocess execution and cancellation behavior: `script_worker.py`.
