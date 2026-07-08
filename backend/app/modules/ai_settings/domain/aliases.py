"""Alias allowlist per task family (ADR-0011 §1).

An admin may select only an allowlisted alias NAME per task family — never free
text. This blocks raw ``vendor/model-path`` injection (which ``output_guard``
would otherwise have to scrub) and keeps the alias→concrete-model mapping in
env/config (the deferred ``ai_task_model_configs`` job). Every allowlisted alias
is asserted gateway-resolvable (``openai_compatible.known_aliases``) so an admin
can never persist a selection the gateway cannot resolve.

The allowlist exposes alias NAMES only — the frontend renders these in selectors
with NO provider/model id ever revealed.
"""

from __future__ import annotations

from app.ai.gateway.openai_compatible import known_aliases

# task family -> selectable alias names. Kept inside the gateway-resolvable set.
ALIAS_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "chat": ("chat_default", "chat_openai_fast", "chat_openai_best", "chat_local"),
    "reasoning": ("reasoning_default", "reasoning_local"),
    "embedding": ("embedding_default", "embedding_openai", "embedding_local"),
    "rerank": ("rerank_default", "rerank_openai_fast", "rerank_local"),
    "eval": ("eval_default", "eval_local"),
}

# Maps each editable column to its task family for validation/presentation.
ALIAS_FIELDS: dict[str, str] = {
    "chat_model_alias": "chat",
    "reasoning_model_alias": "reasoning",
    "embedding_model_alias": "embedding",
    "rerank_model_alias": "rerank",
    "eval_model_alias": "eval",
}


def allowed_aliases(field: str) -> tuple[str, ...]:
    """Allowlisted alias names for an alias column (empty tuple if unknown field)."""

    family = ALIAS_FIELDS.get(field)
    if family is None:
        return ()
    return ALIAS_ALLOWLIST[family]


def is_allowed(field: str, alias: str) -> bool:
    """True when ``alias`` is allowlisted for the alias column ``field``."""

    return alias in allowed_aliases(field)


def assert_allowlist_resolvable() -> None:
    """Invariant: every allowlisted alias is gateway-resolvable. Called by tests."""

    resolvable = known_aliases()
    for aliases in ALIAS_ALLOWLIST.values():
        for alias in aliases:
            if alias not in resolvable:  # pragma: no cover - guarded by a unit test
                raise AssertionError(f"allowlisted alias not gateway-resolvable: {alias}")
