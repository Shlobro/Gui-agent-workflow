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
- Cancellation attempts graceful terminate first, then force-kills if needed.

## When To Edit
- Timeout/cancellation semantics: `llm_worker.py`.
- CLI invocation behavior or cwd handling: `llm_worker.py` plus provider files in `src/llm/`.
