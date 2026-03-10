# dialogs Developer Guide

## Purpose
Hosts modal dialog classes used by `MainWindow` for user-facing runtime notifications and run setup that require explicit user input.

## Contents
- `usage_limit_dialog.py`: `UsageLimitDialog(QDialog)` shown when an LLM CLI subprocess exits with a non-zero return code and output matches a known usage/rate-limit pattern. Presents node name and truncated error text with two choices: `CHANGE_MODEL` and `STOP_WORKFLOW`.
- `prompt_injection_dialog.py`: Prompt injection configuration dialogs. `PromptTemplateManagerDialog` manages saved templates, default enabled state, and per-template placement (`prepend`/`append`). `PromptInjectionRunDialog` configures template toggles plus one-off text and one-off placement for the next run only.
- `__init__.py`: Package marker.

## Usage Pattern
```python
from src.gui.dialogs.prompt_injection_dialog import (
    PromptInjectionRunDialog,
    PromptTemplateManagerDialog,
)
from src.gui.dialogs.usage_limit_dialog import UsageLimitDialog
```

## Styling
- All dialogs in this package use inline dark-theme stylesheets that match the main application window.
- Prompt injection dialogs style editable lists, placement `QComboBox` controls, and text editors for template content and one-off context input.

## When to Edit
- Adjust usage/rate-limit dialog layout or messaging: `usage_limit_dialog.py`.
- Adjust template CRUD, placement controls, and next-run injection controls: `prompt_injection_dialog.py`.
