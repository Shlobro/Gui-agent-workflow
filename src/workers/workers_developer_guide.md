# workers Developer Guide

## Purpose
Hosts threaded execution logic so LLM CLI calls do not block the Qt event loop.

## Contents
- `llm_worker.py`: `QThread` wrapper that starts provider subprocesses, streams line output, enforces timeout, and supports cancellation.
- `__init__.py`: Package marker.

## Key Behavior
- Worker receives a `BaseLLMProvider` instance, prompt, model id, optional working directory, and timeout.
- Prompt text is written to subprocess stdin.
- Stdout and stderr are merged and emitted line-by-line through `output_line`.
- Completion emits `finished(full_output)`; failures emit `error(message)`.
- Cancellation: `cancel()` is non-blocking — it sets a flag and spawns a daemon watchdog thread that runs terminate→wait(4s)→kill, guaranteeing the subprocess dies and the pipe closes even if the worker thread is blocked in `readline()`. The worker thread always emits `error("Cancelled")` on every cancelled exit path, guaranteeing a terminal signal. The canvas uses this signal solely for ref-cleanup and ignores it as a real failure (stale callbacks are filtered by `run_id` and `_current_run_exec_ids`).

## When To Edit
- Timeout/cancellation semantics: `llm_worker.py`.
- CLI invocation behavior or cwd handling: `llm_worker.py` plus provider files in `src/llm/`.
