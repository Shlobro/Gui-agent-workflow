# variables Developer Guide

## Purpose
`variables/` contains the variable-node UI pieces used for downstream prompt substitution in LLM nodes.

## Files
- `variable_node.py`: `VariableNode` graphics item plus validation helpers for Python-style variable names and numeric values.
- `panel_form.py`: `_VariableForm`, the properties-panel editor for variable title/name/type/value and non-blocking warning text.
- `__init__.py`: Convenience re-exports for the variable node package.

## Rules
- Variable names follow Python identifier rules and reject keywords.
- The node stores the raw user-entered value string even when the type is `number`; numeric validation only checks that the string parses as a number.
- Variable substitution is downstream-only and currently applies only to LLM prompt text.
