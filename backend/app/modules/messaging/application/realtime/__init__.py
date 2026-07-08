"""Realtime fan-out for messaging (WebSocket signals).

Persist-before-deliver (`.claude/rules/realtime.md`): the product write commits first,
then a LIGHTWEIGHT signal (``{type, thread_id}`` — never message content) is published
to the recipients' channels. Clients refetch the thread on a signal, so per-viewer
identity masking is applied server-side and never leaks over the socket. A single
in-process bus serves single-worker local dev; a Redis adapter fans out across workers
when ``messaging_redis_url`` is configured.
"""

from app.modules.messaging.application.realtime.hub import (
    channels_for_thread,
    connection_manager,
    publish_signal,
    shutdown_bus,
    startup_bus,
)

__all__ = [
    "channels_for_thread",
    "connection_manager",
    "publish_signal",
    "shutdown_bus",
    "startup_bus",
]
