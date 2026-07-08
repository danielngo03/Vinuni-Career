"""Mock Interview module.

Student-facing AI mock-interview practice grounded on a real job's JD and the
student's chosen CV. An HR-style interviewer asks specialized, CV-and-JD-grounded
questions with natural follow-ups; there is NO scoring — the student receives
coaching (how to answer better, observations, gaps to work on).

Layers (``.claude/rules/backend.md``):
- ``api`` — HTTP only.
- ``application`` — use cases, RBAC, transactions, quota/caps.
- ``domain`` — pure models/invariants.
- ``infrastructure`` — repositories/adapters (reserved).

The feature is entirely separate from ``recruitment`` real interviews (tables,
module, and semantics). Partners have NO access. University staff get aggregate
governance only; superadmin/AI-ops get pseudonymized observability with audited
full-transcript access for debugging AI quality.
"""
