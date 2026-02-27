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
- Cancellation: `cancel()` is non-blocking — it sets a flag and spawns a daemon watchdog thread that runs terminate→wait(4s)→kill, guaranteeing the subprocess dies and the pipe closes even if the worker thread is blocked in `readline()`. The worker thread always emits `error("Cancelled")` on every cancelled exit path, guaranteeing a terminal signal. The canvas ignores cancelled callbacks as real failures; three guards filter unwanted mutations: (1) `_active_workers` membership is the double-call gate in `_on_invocation_done`; (2) `run_id`/`_running` skip terminal callbacks from a previous run; (3) `_retired_exec_ids` suppresses both streamed output (`on_output`) and terminal node mutation for exec_ids whose node was deleted mid-run — those callbacks still clean up refs and call `_check_drain()`.

## When To Edit
- Timeout/cancellation semantics: `llm_worker.py`.
- CLI invocation behavior or cwd handling: `llm_worker.py` plus provider files in `src/llm/`.
