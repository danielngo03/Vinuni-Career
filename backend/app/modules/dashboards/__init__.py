"""Persona dashboard read-model module.

Assembles per-persona command-center payloads (``student`` / ``partner`` /
``university``) by composing existing per-module application-layer read facades.
Owns no ORM models and runs no migration — see :mod:`dashboards.application` for
the read strategy and staleness contract.
"""
