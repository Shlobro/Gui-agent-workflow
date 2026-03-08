# dialogs Developer Guide

## Purpose
Hosts modal dialog classes used by `MainWindow` for user-facing runtime notifications that require an explicit response before the application can continue.

## Contents
- `usage_limit_dialog.py`: `UsageLimitDialog(QDialog)` — shown when an LLM CLI subprocess exits with a non-zero return code and the output matches a known usage/rate-limit pattern. Presents the node name and a truncated (≤300 chars) error message with two choices: **Change Model** (`CHANGE_MODEL = 0`) and **Stop Workflow** (`STOP_WORKFLOW = 1`). The chosen code is read via `result_code() -> int` after `exec()` returns.
- `__init__.py`: Package marker.

## Usage Pattern
```python
from src.gui.dialogs.usage_limit_dialog import UsageLimitDialog

dlg = UsageLimitDialog(node_title="My LLM Node", error_text=raw_error, parent=self)
dlg.exec()
if dlg.result_code() == UsageLimitDialog.CHANGE_MODEL:
    # select node and open the properties panel
```

## Styling
`UsageLimitDialog` is self-styled with an inline stylesheet matching the app's dark theme (`background: #1e1e1e`, `color: #e8e8e8`). The **Change Model** button has a blue accent (`#1a4a8a` / border `#3a8ef5`). The error text block uses a monospace label with a dark-red tint to make CLI output legible.

## When to Edit
- Adjust text or button labels: `usage_limit_dialog.py`.
- Add new runtime dialogs: create a new file in this package and import it from `main_window.py`.
