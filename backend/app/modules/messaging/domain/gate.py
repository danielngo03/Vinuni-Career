"""The first-contact "message request" gate — PURE state machine, no I/O.

Owner decision 2026-07-09 (`docs/superpowers/specs/2026-07-09-messaging-v2-design.md`):
a NEW conversation between two parties who have never had an accepted thread starts
``pending``. While pending only the INITIATOR may post, capped at ``limit`` intro
messages, until the recipient party **accepts** (→ unlimited both ways), **declines**
(→ initiator stops), or **blocks** (→ initiator cannot re-initiate). The gate is
SKIPPED (thread opens ``accepted``) for privileged / consented axes:

- the initiator is a **university** Page (the platform owner messages instantly);
- an **internal** same-org thread (colleagues / department);
- a partner↔student thread backed by an **active application** (recruitment consent);
- a prior **accepted** thread already exists between the two parties.

The service layer resolves those facts and feeds them here; this module never touches
the database and returns only stable internal tokens.
"""

from __future__ import annotations

from app.modules.messaging.domain import rules


def should_gate(
    *,
    initiator_is_university: bool,
    is_internal: bool,
    is_application: bool,
    prior_accepted_exists: bool,
) -> bool:
    """True when a new thread must start ``pending`` (needs recipient acceptance)."""

    if initiator_is_university:
        return False
    if is_internal:
        return False
    if is_application:
        return False
    if prior_accepted_exists:
        return False
    return True


def initial_request_state(
    *,
    initiator_is_university: bool,
    is_internal: bool,
    is_application: bool,
    prior_accepted_exists: bool,
) -> str:
    return (
        rules.REQUEST_PENDING
        if should_gate(
            initiator_is_university=initiator_is_university,
            is_internal=is_internal,
            is_application=is_application,
            prior_accepted_exists=prior_accepted_exists,
        )
        else rules.REQUEST_ACCEPTED
    )


def evaluate_request_send(
    *,
    request_state: str,
    sender_is_initiator: bool,
    request_message_count: int,
    limit: int,
) -> str | None:
    """Gate a send against the request state. ``None`` = allowed, else a reason code.

    - ``accepted``: no gate (other limits still apply upstream).
    - ``pending``: only the initiator may post, and only up to ``limit`` intro
      messages; the recipient must accept first before they (or the initiator beyond
      the cap) may continue.
    - ``declined`` / ``blocked``: nobody may post.
    """

    if request_state == rules.REQUEST_ACCEPTED:
        return None
    if request_state == rules.REQUEST_DECLINED:
        return rules.REASON_REQUEST_DECLINED
    if request_state == rules.REQUEST_BLOCKED:
        return rules.REASON_REQUEST_BLOCKED
    # pending
    if not sender_is_initiator:
        # The recipient cannot reply until they accept (accepting is the reply path).
        return rules.REASON_REQUEST_PENDING_LIMIT
    if request_message_count >= max(0, limit):
        return rules.REASON_REQUEST_PENDING_LIMIT
    return None


def can_respond_to_request(*, request_state: str, actor_is_recipient: bool) -> bool:
    """Only the RECIPIENT party of a still-``pending`` request may accept/decline/block."""

    return request_state == rules.REQUEST_PENDING and actor_is_recipient


# The RECIPIENT party controls the request gate across the whole conversation life,
# not only at first contact (owner decision 2026-07-09 — a full, reversible block
# lifecycle). Valid recipient-driven transitions:
#   accept  : (re)open           pending / declined            -> accepted
#   decline : soft no            pending                       -> declined
#   block   : hard stop (silent) pending / declined / accepted -> blocked
#   unblock : lift the block     blocked                       -> declined
# `accept` deliberately excludes `blocked` (unblock first) and a no-op re-`accept`;
# the initiator never drives these — only the party who received the outreach.
_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "accept": (
        frozenset({rules.REQUEST_PENDING, rules.REQUEST_DECLINED}),
        rules.REQUEST_ACCEPTED,
    ),
    "decline": (frozenset({rules.REQUEST_PENDING}), rules.REQUEST_DECLINED),
    "block": (
        frozenset(
            {rules.REQUEST_PENDING, rules.REQUEST_DECLINED, rules.REQUEST_ACCEPTED}
        ),
        rules.REQUEST_BLOCKED,
    ),
    "unblock": (frozenset({rules.REQUEST_BLOCKED}), rules.REQUEST_DECLINED),
}

REQUEST_ACTIONS = frozenset(_TRANSITIONS)


def request_transition(*, current_state: str, action: str) -> str | None:
    """Resolve a recipient request action to its NEW state, or ``None`` if the action
    is not valid from ``current_state`` (unknown action, or an illegal transition)."""

    entry = _TRANSITIONS.get(action)
    if entry is None:
        return None
    allowed_from, new_state = entry
    return new_state if current_state in allowed_from else None
