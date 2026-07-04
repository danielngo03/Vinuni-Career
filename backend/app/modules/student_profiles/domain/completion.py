"""Profile-completion scoring (pure domain rule).

``docs/BUSINESS_LOGIC.md`` describes profile completeness as a 0-100 signal driving
student dashboard nudges and passive-search ranking but does not fix the weights;
this module pins an explicit, documented weighting so the value is deterministic
and testable. The cache (``student_profiles.profile_completion``) is refreshed by
the service on every write.

Weights (sum = 100):

    headline filled .................... 15
    summary filled ..................... 15
    >= 1 education entry ............... 20
    >= 1 experience entry ............. 15
    >= 3 skills ....................... 15
    >= 1 link ......................... 10
    open-to-work configured ........... 10   (is_open_to_work + >=1 type)

The function takes plain counts/flags so it is trivially unit-testable and never
touches the ORM or a session.
"""

from __future__ import annotations

from dataclasses import dataclass

W_HEADLINE = 15
W_SUMMARY = 15
W_EDUCATION = 20
W_EXPERIENCE = 15
W_SKILLS = 15
W_LINKS = 10
W_OPEN_TO_WORK = 10

SKILLS_TARGET = 3


@dataclass(slots=True)
class CompletionInputs:
    has_headline: bool
    has_summary: bool
    education_count: int
    experience_count: int
    skill_count: int
    link_count: int
    open_to_work_configured: bool


def compute(inputs: CompletionInputs) -> int:
    """Return the 0-100 completion score for the given profile state."""

    score = 0
    if inputs.has_headline:
        score += W_HEADLINE
    if inputs.has_summary:
        score += W_SUMMARY
    if inputs.education_count >= 1:
        score += W_EDUCATION
    if inputs.experience_count >= 1:
        score += W_EXPERIENCE
    if inputs.skill_count >= SKILLS_TARGET:
        score += W_SKILLS
    if inputs.link_count >= 1:
        score += W_LINKS
    if inputs.open_to_work_configured:
        score += W_OPEN_TO_WORK
    return min(score, 100)
