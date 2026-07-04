"""AI assistant tool sub-package.

Public API (backward-compatible with tool_registry imports):
    ToolSpec, TOOL_SPECS — declarative tool registry
    dispatch_tool        — async router
"""

from .dispatch import dispatch_tool
from .specs import TOOL_SPECS, ConfirmationCopy, ToolSpec

__all__ = ["ToolSpec", "ConfirmationCopy", "TOOL_SPECS", "dispatch_tool"]
