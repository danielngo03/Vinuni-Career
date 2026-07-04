"""Generalized cross-module import boundary guard (`docs/ARCHITECTURE.md` §8).

Scans every module's ``application/`` and ``api/`` packages for
``from app.modules.<other>.domain...`` / ``from app.modules.<other>.infrastructure...``
imports of a SIBLING module (never its own) and fails if any are found outside a
narrow, explicitly-justified allowlist. Modules communicate through
application-layer read/write facades (``*_read_facade.py``, ``*_facade.py``,
service modules) instead — never by reaching into another module's ORM/domain
models or infrastructure adapters directly.

This generalizes/extends the two hand-written single-pair guards already shipped
(``test_advertising.test_advertising_does_not_import_opportunities_orm`` and
``test_billing.test_documents_only_imports_the_billing_limit_facade``), which stay
in place unchanged; this test covers every OTHER module pair.

Allowlist policy:

- ``app.shared`` / ``app.core`` / ``app.ai`` are shared platform code, not a
  product module — always allowed.
- A module importing its OWN submodules is never an offense (filtered out before
  the forbidden-prefix check even applies).
- The previous four call sites here (``account_service`` reaching into
  ``auth.domain.models``/``auth.infrastructure`` for session/password/TOTP
  writes, and ``auth_service``/``presenters`` reaching into
  ``users.domain.models`` for registration's User/Identity/UserPreference
  creation) have been closed via dedicated facades —
  ``auth.application.session_facade``/``password_facade``/``totp_facade`` and
  ``users.application.user_write_facade`` — so ``_KNOWN_EXCEPTIONS`` is now
  empty. Any new entry must be narrowly allowlisted by exact file path, not by
  module pair, so no new offender can silently ride along.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_ROOT = pathlib.Path("app/modules")

# Modules whose cross-module ORM/infrastructure reach is already covered by a
# DEDICATED hand-written guard test elsewhere (kept as-is; not re-asserted here
# to avoid duplicate/conflicting expectations if that test's shape evolves).
_COVERED_ELSEWHERE = {
    ("advertising", "opportunities"),
    ("documents", "billing"),
}

# (importing_file, forbidden_module_prefix): a known, deliberately-left exception.
# Each entry MUST have a one-line reason and a named follow-up owner/shape.
#
# Empty as of the auth.application.session_facade/password_facade/totp_facade +
# users.application.user_write_facade follow-up: account's session/password/TOTP
# settings UI and auth's registration/login flow now go through those facades
# instead of reaching into the sibling module's domain/infrastructure directly.
_KNOWN_EXCEPTIONS: dict[tuple[str, str], str] = {}


def _module_of(path: pathlib.Path) -> str:
    # app/modules/<mod>/... -> <mod>
    return path.parts[2]


def _imported_prefixes(tree: ast.AST) -> list[str]:
    prefixes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            prefixes.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                prefixes.append(alias.name)
    return prefixes


_FORBIDDEN_SUFFIXES = ("domain.models", "domain.event_models", "infrastructure")


def _is_forbidden(prefix: str, *, own_module: str) -> str | None:
    """Return the forbidden module dotted-path if ``prefix`` is a sibling-module
    domain/infrastructure reach, else ``None``."""

    if not prefix.startswith("app.modules."):
        return None
    rest = prefix[len("app.modules.") :]
    parts = rest.split(".")
    other_module = parts[0]
    if other_module == own_module:
        return None
    remainder = ".".join(parts[1:])
    for suffix in _FORBIDDEN_SUFFIXES:
        if remainder == suffix or remainder.startswith(suffix + "."):
            return f"app.modules.{other_module}.{suffix}"
    return None


def _scan() -> list[str]:
    offenders: list[str] = []
    for sub in ("application", "api"):
        for path in _ROOT.glob(f"*/{sub}/**/*.py"):
            own_module = _module_of(path)
            tree = ast.parse(path.read_text())
            for prefix in _imported_prefixes(tree):
                forbidden = _is_forbidden(prefix, own_module=own_module)
                if forbidden is None:
                    continue
                other_module = forbidden.split(".")[2]
                if (own_module, other_module) in _COVERED_ELSEWHERE or (
                    other_module,
                    own_module,
                ) in _COVERED_ELSEWHERE:
                    continue
                key = (str(path).replace("\\", "/"), forbidden)
                if key in _KNOWN_EXCEPTIONS:
                    continue
                offenders.append(f"{path}: {prefix}")
    return offenders


def test_no_undocumented_cross_module_domain_or_infrastructure_imports() -> None:
    offenders = _scan()
    assert offenders == [], (
        "Cross-module domain/infrastructure import(s) found. Communicate via an "
        "application-layer read/write facade instead (see docs/ARCHITECTURE.md "
        "§8), or add a justified, narrowly-scoped entry to _KNOWN_EXCEPTIONS "
        "in this test if truly unavoidable:\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("key", sorted(_KNOWN_EXCEPTIONS))
def test_known_exceptions_are_still_present_and_narrow(key: tuple[str, str]) -> None:
    """Each documented exception must still exist verbatim (path + prefix).

    If this starts failing, the exception was already closed by a facade — remove
    the (now-stale) allowlist entry from ``_KNOWN_EXCEPTIONS`` above.
    """

    path_str, forbidden_prefix = key
    path = pathlib.Path(path_str)
    assert path.exists(), f"{path} no longer exists; remove the stale exception"
    tree = ast.parse(path.read_text())
    own_module = _module_of(path)
    found = any(
        _is_forbidden(prefix, own_module=own_module) == forbidden_prefix
        for prefix in _imported_prefixes(tree)
    )
    assert found, (
        f"{path} no longer imports {forbidden_prefix} — the exception in "
        "_KNOWN_EXCEPTIONS is stale and should be removed"
    )
