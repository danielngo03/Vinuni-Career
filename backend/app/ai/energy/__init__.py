"""AI energy metering — the persona-agnostic quota meter.

The single place that answers "does this actor have AI budget left, and how
much". Consumption is measured in cost-weighted **credits** (never shown to end
users) sourced from the durable ``ai_billable_usage`` ledger; the user-facing
surface is an **AI energy %** (remaining / allowance). Tokens, USD, provider,
and model are NEVER exposed here — those stay superadmin-only
(``docs/AI_PRODUCT_SPEC.md`` §15, ``CLAUDE.md`` hidden-internals rule).

Windows (owner-locked 2026-07-08, shared by student + partner):
- **weekly = HARD block** — the real budget; exhaustion routes to upgrade / top-up
  (student/partner) or an admin limit request (university staff).
- **3h rolling = SOFT warn only** — burst protection; never blocks.
- **daily = REMOVED** — neither a request-count nor a USD daily gate.

Quota resolution chain (partner): plan-derived ORG pool → admin sub-allocation to
department/user → the actor's own non-resetting top-up **wallet**. Students meter
on their own user scope. See :mod:`app.ai.energy.service`.
"""
