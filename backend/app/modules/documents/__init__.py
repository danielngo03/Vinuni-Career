"""
Documents module — upload sessions, ACL, scan lifecycle, document versioning.

This module owns the full lifecycle of user-uploaded files:
  PENDING_UPLOAD → UPLOADED → SCANNING → CLEAN / INFECTED / SCAN_ERROR → EXPIRED

Key design decisions:
- Partners/students never touch raw storage keys — only presigned URLs.
- ACL check: document belongs to owner; university admin can read any doc in their org.
- Scan adapter is injected (ClamAV in production, mock in dev/test).
- Documents module does NOT depend on any other business module.
"""
from __future__ import annotations
