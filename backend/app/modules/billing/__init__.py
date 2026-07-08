"""Billing module: tiered subscription plans + manual/bank-transfer billing.

See ``docs/adr/ADR-0010-subscriptions-and-manual-billing.md``. Mirrors the shipped
ADR-0009 advertising manual-billing pattern (seeded reference tiers, a lifecycle
entity with a frozen price snapshot + manual ``mark_paid``, a university-only
oversight gate, ADR-0003 scheduler sweeps, and a revenue roll-up) and exposes the
single one-way ``documents -> billing`` limit-resolution facade.
"""
