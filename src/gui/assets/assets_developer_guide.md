# assets Developer Guide

## Purpose
`src/gui/assets/` stores static image assets used by the GUI at runtime.

## Contents
- `claude_logo.png`: Anthropic/Claude logo used in the model dropdown.
- `gemini_logo.png`: Gemini logo used in the model dropdown.
- `openai_logo.png`: OpenAI logo used in the model dropdown.

## Usage
- `src/gui/bubble_widget.py` loads these files through `QIcon` to render provider logos in the model selector.
- Icons are normalized to a fixed 16x16 canvas while preserving aspect ratio, so source images can have different dimensions.
- Keep file names stable because icon lookup is path-based.
