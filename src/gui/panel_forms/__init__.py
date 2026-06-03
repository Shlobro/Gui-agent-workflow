"""Form widget classes used by PropertiesPanel (one form per node type).

Split across modules to keep each file under the size cap: the LLM-call form
lives in ``llm_form`` and the remaining node forms in ``node_forms``.
"""

from .llm_form import _LLMForm
from .node_forms import (
    _AttentionForm,
    _ConditionalForm,
    _FileOpForm,
    _GitActionForm,
    _JoinForm,
    _LoopForm,
    _ScriptForm,
)

__all__ = [
    "_LLMForm",
    "_AttentionForm",
    "_ConditionalForm",
    "_FileOpForm",
    "_GitActionForm",
    "_JoinForm",
    "_LoopForm",
    "_ScriptForm",
]
