"""AI assistant tool registry — re-export facade.

The implementation is split across
``app.modules.ai_assistant.application.tools.*`` for maintainability.
This module exists purely for backward-compatible imports.

Mutating tools require ``permission_class="confirmation_required"`` and are
dispatched only after explicit user confirmation (AI_PRODUCT_SPEC.md §4.3).
"""

from __future__ import annotations

from app.modules.ai_assistant.application.tools import (  # noqa: F401
    TOOL_SPECS,
    ConfirmationCopy,
    ToolSpec,
    dispatch_tool,
)
