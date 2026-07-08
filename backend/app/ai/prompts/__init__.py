"""Versioned AI prompt templates (owned by ai-engineer).

Layout: ``backend/app/ai/prompts/{task_name}/v{N}.py`` (``docs/AI_PRODUCT_SPEC.md``
§8.1). The static identity + safety rules block lives in ``cv_common`` and is
placed FIRST in every message list (cache-eligible static prefix; never put user
content before it — §8.2).
"""
