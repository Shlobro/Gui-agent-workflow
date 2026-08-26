# panel_forms Developer Guide

## Purpose
Holds the per-node form widget classes that `PropertiesPanel` stacks and shows for the selected workflow node. Split into modules so no single file approaches the size cap.

## Files
- `llm_form.py`: `_LLMForm` — the LLM-call editor. Owns the two-stage model selection (Model dropdown plus a dependent Effort dropdown that only appears for models with variants), the account-profile dropdown, the session controls (resume/save/restart/named-resume), per-node prompt-template `Prepend`/`Append` dropdowns, the Prompt/Prompt-Preview tabs, the variable-warning note, and the per-call `Call N` output tabs.
- `node_forms.py`: The remaining node forms — `_FileOpForm`, `_ConditionalForm`, `_LoopForm`, `_JoinForm`, `_GitActionForm`, `_AttentionForm`, and `_ScriptForm`.
- `__init__.py`: Re-exports every form class so importers use `from .panel_forms import _LLMForm, ...`.

## Conventions
- Each form is a plain `QWidget` with public widget attributes (e.g. `title_edit`, `model_selector`) that `PropertiesPanel` wires to signals and reads/writes directly.
- Forms expose `show_output(visible)` and small `set_*`/`current_*` state methods rather than reaching into child widgets from outside.
- `_LLMForm.set_profile_state(visible, options, selected_name)` populates the profile dropdown; `current_profile_name()` reads the selected value (empty string = default account). The widget is hidden for providers without profile support.
- Model/effort state flows through composed ids (`<model>:<variant>`): `set_model_state(full_id)` loads a stored id into both selectors without emitting, `current_full_model_id()` returns the current composition, and the `model_selection_changed(str)` signal fires only for user-driven changes. Variant options come from the provider catalog via `variant_options_for`/`default_variant_for` in `llm_widget.py`.

## When To Edit
- Change an LLM-call control's layout or state API: `llm_form.py`.
- Change any non-LLM node form: `node_forms.py`.
- Add or remove a form class: update the class module and the `__init__.py` re-exports.
