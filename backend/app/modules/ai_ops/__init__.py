"""AI Operations admin module.

Provides superadmin-only read APIs over AI telemetry:
overview, spend, reliability, volume, and events.
Provider/model identity is masked unless the caller holds
the ``ai_settings:view_provider_identity`` permission.
"""
