"""Offline AI evaluation harness + datasets (CI gate, ``docs/AI_PRODUCT_SPEC.md`` §10).

Datasets live under ``datasets/{task_name}/`` in five categories: happy_path,
adversarial, privacy_boundary, low_quality_input, fallback. They run with the
offline provider (no network, no keys). See ``EVAL_NOTES.md``.
"""
