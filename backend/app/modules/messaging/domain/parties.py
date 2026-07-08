"""Pure helpers for the party model + identity masking decisions (Messaging V2).

No I/O. The service resolves personas / org membership / relationship facts and the
projection (``thread_view``) calls these to decide how a party renders. Keeping the
decision here (not scattered across services) is what makes the org-Page masking
impossible to diverge between the inbox list, the thread detail, the message echo,
and the notification label.
"""

from __future__ import annotations

from app.modules.messaging.domain import rules

# Personas that act AS an organization Page (their identity is masked to outsiders).
_ORG_SIDE = frozenset({rules.PARTNER_MEMBER, rules.UNIVERSITY_STAFF})


def identity_mode_for_persona(persona: str) -> str:
    """An org-side persona renders as the org Page; an individual renders as a person."""

    return rules.IDENTITY_ORG if persona in _ORG_SIDE else rules.IDENTITY_PERSON


def is_org_side(persona: str) -> bool:
    return persona in _ORG_SIDE


def thread_kind_for(
    *,
    sender_persona: str,
    recipient_personas: list[str],
    kind: str,
    same_org: bool,
    is_application: bool,
) -> str:
    """Derive the V2 ``thread_kind`` discriminator from the resolved facts."""

    if kind == rules.KIND_ANNOUNCEMENT:
        return rules.TK_ANNOUNCEMENT
    if is_application:
        return rules.TK_APPLICATION
    sender_org = is_org_side(sender_persona)
    all_recip_org = bool(recipient_personas) and all(
        is_org_side(p) for p in recipient_personas
    )
    any_recip_org = any(is_org_side(p) for p in recipient_personas)
    # Internal: everyone shares the sender's org.
    if sender_org and all_recip_org and same_org:
        return rules.TK_INTERNAL
    # Page ↔ Page across orgs (e.g. university ↔ partner).
    if sender_org and all_recip_org and not same_org:
        return rules.TK_ORG_TO_ORG
    # Individual ↔ org Page (student ↔ partner/university), either direction.
    if sender_org != any_recip_org:
        return rules.TK_ORG_DM
    return rules.TK_ORG_DM


def student_masked_to_partner_pending(
    *,
    thread_request_state: str,
    org_is_initiator: bool,
) -> bool:
    """A cold partner-initiated request keeps the student masked until they accept.

    (A student-initiated request does NOT mask the student — they chose to reach out,
    so the org may see their name to help them: the asymmetric identity decision.)
    """

    return (
        thread_request_state == rules.REQUEST_PENDING and org_is_initiator
    )
