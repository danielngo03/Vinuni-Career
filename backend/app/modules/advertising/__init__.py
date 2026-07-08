"""Advertising — sponsored / featured placements (ADR-0009, V1 manual-billed).

A partner *requests to sponsor / feature one of their own jobs or events* for a
paid, date-windowed, university-approved period. ``sponsored_placements`` is the
**source of truth** for sponsorship; the shipped ``jobs/events.is_sponsored`` /
``is_featured`` columns are a **rendered projection** recomputed from active
placements through the one-way ``opportunities.sponsorship_facade`` setter.

Disclosure is non-negotiable: the only mechanism that turns a flag on is placement
activation, which drives the existing mandatory ``Được tài trợ`` / ``Nổi bật``
label — no field, endpoint, or state in this module can render sponsored content
without it.
"""
